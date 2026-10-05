"""Read-only review of pinned local reference runs; never changes dispositions."""

import argparse
import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from detector_acceptance import ROOT, artifact_path, digest, observe

from mediaqc_engine.media.inspection import fingerprint

type Document = dict[str, Any]


def overlap(finding: Document, interval: Document) -> bool:
    start, end = finding.get("start_time_seconds"), finding.get("end_time_seconds")
    if start is None or end is None:
        return True  # Whole-stream findings cannot escape a scoped negative check.
    return bool(
        start <= interval["end_time_seconds"] and end >= interval["start_time_seconds"]
    )


def assess(reference: Document, findings: list[Document], states: Document) -> Document:
    """Annotations explain results, but never suppress a failed negative assertion."""
    errors = []
    for interval in reference.get("negative_intervals", []):
        for detector in interval["detectors"]:
            if states.get(detector) != "COMPLETED":
                errors.append(f"{detector}: negative interval was not measured")
            for finding in findings:
                if finding["detector_id"] == detector and overlap(finding, interval):
                    errors.append(f"Known-good {interval['intent']}: {finding['id']}")
    annotations = reference.get("finding_reviews", {})
    reviewed = []
    for finding in findings:
        review = annotations.get(
            finding["id"], {"classification": "C", "reason": "Unreviewed finding"}
        )
        if review["classification"] not in {"A", "B", "C", "D"}:
            raise ValueError("Unknown review classification")
        if review["classification"] == "D":
            errors.append(f"Confirmed reference false positive: {finding['id']}")
        reviewed.append({**finding, "review": review})
    missing = set(annotations) - {f["id"] for f in findings}
    if missing:
        errors.append(f"Reviewed findings missing from pinned run: {sorted(missing)}")
    unresolved = sum(f["review"]["classification"] == "C" for f in reviewed)
    return {
        "status": "FAIL" if errors else "UNRESOLVED" if unresolved else "REVIEWED",
        "errors": errors,
        "unresolved_count": unresolved,
        "findings": reviewed,
        "note": "Saved-run review; not fresh execution or clean-corpus certification.",
    }


def review_database(manifest: Document) -> Document:
    if manifest.get("schema_version") != "1.0.0" or manifest.get("ai_mode") != "OFF":
        raise ValueError("Reference review requires schema 1.0.0 and AI OFF")
    database = Path(manifest["database"]).resolve()
    before = digest(database)
    reports = []
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        for reference in manifest["references"]:
            row = connection.execute(
                "SELECT r.*,m.absolute_path,m.file_name FROM analysis_runs r "
                "JOIN media_assets m ON m.id=r.media_asset_id WHERE r.id=?",
                (reference["run_id"],),
            ).fetchone()
            if row is None or row["status"] != "COMPLETED" or row["ai_mode"] != "OFF":
                raise ValueError(
                    "Pinned reference run is absent, incomplete or not AI OFF"
                )
            source = Path(reference["source"]).resolve()
            if source != Path(row["absolute_path"]).resolve():
                raise ValueError("Reference source does not match pinned run")
            identity = fingerprint(source)
            if identity["fast_fingerprint_sha256"] != row["media_fingerprint_sha256"]:
                raise ValueError("Reference source changed since pinned run")
            if row["media_fingerprint_sha256"] != reference["fast_fingerprint_sha256"]:
                raise ValueError("Manifest identity differs from pinned run")
            profile = json.loads(row["qc_profile_snapshot_json"])
            if profile != manifest["profile_snapshot"]:
                raise ValueError("Pinned run does not use the reviewed profile")
            findings = []
            for f in connection.execute(
                "SELECT f.*,s.stream_index FROM findings f LEFT JOIN media_streams s "
                "ON s.id=f.stream_id WHERE f.analysis_run_id=? "
                "ORDER BY f.detector_id,f.id",
                (row["id"],),
            ):
                item = dict(f)
                for field in ("measurements", "threshold", "metadata"):
                    item[field] = json.loads(item.pop(field + "_json") or "null")
                findings.append(item)
            executions = [
                dict(d)
                for d in connection.execute(
                    "SELECT detector_id,detector_version,status,metrics_json "
                    "FROM detector_executions "
                    "WHERE analysis_run_id=?",
                    (row["id"],),
                )
            ]
            states = {d["detector_id"]: d["status"] for d in executions}
            report = assess(reference, findings, states)
            reports.append(
                {
                    "reference_id": reference["reference_id"],
                    "run_id": row["id"],
                    "saved_verdict": row["overall_result"],
                    "identity": identity,
                    "assignments": reference["assignments"],
                    "executions": executions,
                    **report,
                }
            )
        connection.rollback()
    finally:
        connection.close()
    if before != digest(database):
        raise AssertionError(
            "Reference database changed during review; retry with a stable project"
        )
    return {
        "schema_version": "1.0.0",
        "database_sha256": before,
        "ai_mode": "OFF",
        "references": reports,
        "historical_verdicts_modified": False,
    }


def replay_negatives(manifest: Document, directory: Path) -> list[Document]:
    """Fresh local detector execution, scoped to owner-reviewed negative windows.

    Saved finding IDs/classifications never filter this result. Unknown audio
    transients are not negative controls. Entire source timelines are retained.
    """
    reports = []
    for reference in manifest["references"]:
        intervals = reference.get("negative_intervals", [])
        if not intervals:
            continue
        source = Path(reference["source"]).resolve()
        if (
            fingerprint(source)["fast_fingerprint_sha256"]
            != reference["fast_fingerprint_sha256"]
        ):
            raise ValueError("Reference identity changed; review again before replay")
        scope = sorted(
            {detector for interval in intervals for detector in interval["detectors"]}
        )
        case = {
            "fixture_id": reference["reference_id"],
            "profile_version": "1.2.0",
            "detectors": scope,
            "expected_findings": [],
        }
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            observation = observe(source, case, Path(temporary))
        if observation["profile"] != manifest["profile_snapshot"]:
            raise ValueError("Replay profile differs from reviewed snapshot")
        errors = list(observation["errors"])
        for interval in intervals:
            for detector in interval["detectors"]:
                if observation["states"].get(detector) != "COMPLETED":
                    errors.append(f"{detector}: negative interval not measured")
                for finding in observation["findings"]:
                    if finding["detector_id"] == detector and overlap(
                        finding, interval
                    ):
                        errors.append(
                            f"{interval['intent']}: {detector} at "
                            f"{finding.get('start_time_seconds')}"
                        )
        reports.append(
            {
                "reference_id": reference["reference_id"],
                "status": "FAIL" if errors else "PASS",
                "errors": errors,
                "observation": observation,
                "note": "Only the declared negative windows were adjudicated.",
            }
        )
    if not reports:
        raise ValueError("No reviewed negative intervals to replay")
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replay-negatives", action="store_true")
    args = parser.parse_args()
    output = artifact_path(args.output)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = review_database(manifest)
    if args.replay_negatives:
        cache = ROOT / ".cache" / "phase12"
        cache.mkdir(parents=True, exist_ok=True)
        report["fresh_negative_replays"] = replay_negatives(manifest, cache)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    for reference in report["references"]:
        print(reference["reference_id"], reference["status"])
    if args.replay_negatives:
        for replay in report["fresh_negative_replays"]:
            print("fresh", replay["reference_id"], replay["status"])
        return int(any(r["status"] != "PASS" for r in report["fresh_negative_replays"]))
    # Unresolved is not a green acceptance result; distinguish it from a failure.
    if any(r["status"] == "FAIL" for r in report["references"]):
        return 1
    return 2 if any(r["status"] == "UNRESOLVED" for r in report["references"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
