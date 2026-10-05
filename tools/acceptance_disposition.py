"""Strict developer-only V1 release dispositions; never imported by the engine."""

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "tests/fixtures/phase12_limitations.json"
MAX_BYTES = 1024 * 1024
RECORD_FIELDS = {
    "fixture_id",
    "classification",
    "risk",
    "reason",
    "evidence",
    "approval",
    "case_sha256",
    "generator_sha256",
    "profile_sha256",
    "detector_versions",
    "tools_sha256",
    "behavior",
}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def behavior(observation: dict[str, Any]) -> dict[str, Any]:
    """Retain every observable field except generated UUIDs and collection order."""
    return {
        "findings": sorted(
            [
                {k: v for k, v in f.items() if k != "id"}
                for f in observation["findings"]
            ],
            key=canonical,
        ),
        "metrics": sorted(observation["metrics"], key=canonical),
        "states": observation["states"],
        "errors": observation["errors"],
        "warnings": observation.get("warnings", {}),
    }


def load(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    with path.open("rb") as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Limitation registry exceeds bound")
    document: dict[str, Any] = json.loads(raw)
    canonical(document)  # Reject NaN/infinity, including inside saved measurements.
    if (
        set(document) != {"schema_version", "records", "unresolved_references"}
        or document["schema_version"] != "1.0.0"
    ):
        raise ValueError("Invalid limitation registry schema")
    records = document["records"]
    if not isinstance(records, list) or not 1 <= len(records) <= 32:
        raise ValueError("Invalid limitation record count")
    seen = set()
    for record in records:
        if set(record) != RECORD_FIELDS or record["fixture_id"] in seen:
            raise ValueError("Invalid or duplicate limitation record")
        seen.add(record["fixture_id"])
        if record["classification"] not in (
            "known_detector_limitation",
            "acceptance_expectation_problem",
        ):
            raise ValueError("Invalid limitation classification")
        if record["risk"] not in (
            "missed_defect",
            "false_positive",
            "unavailable_intent",
        ):
            raise ValueError("Invalid limitation risk")
        if any(
            not isinstance(record[k], str) or not record[k].strip()
            for k in ("fixture_id", "reason", "evidence", "approval")
        ):
            raise ValueError("Limitation review provenance required")
        hashes = [
            record[k] for k in ("generator_sha256", "profile_sha256", "tools_sha256")
        ]
        if (
            not isinstance(record["case_sha256"], list)
            or not 1 <= len(record["case_sha256"]) <= 2
        ):
            raise ValueError("Exact case identities required")
        hashes += record["case_sha256"]
        if any(
            not isinstance(h, str)
            or len(h) != 64
            or any(c not in "0123456789abcdef" for c in h)
            for h in hashes
        ):
            raise ValueError("Invalid binding digest")
        bound = record["behavior"]
        if (
            set(bound) != {"findings", "metrics", "states", "errors", "warnings"}
            or bound["errors"]
            or not bound["states"]
            or any(v != "COMPLETED" for v in bound["states"].values())
        ):
            raise ValueError("Only successful measured executions may be accepted")
        if set(bound["states"]) != set(record["detector_versions"]):
            raise ValueError("Detector binding mismatch")
    references = document["unresolved_references"]
    if not isinstance(references, list) or len(references) != 1:
        raise ValueError("One explicitly unresolved reference required")
    reference = references[0]
    if (
        set(reference)
        != {
            "reference_id",
            "status",
            "blocking",
            "interval_description",
            "evidence",
            "reason",
        }
        or reference["status"] != "NEEDS_INDEPENDENT_EVIDENCE"
        or reference["blocking"] is not False
    ):
        raise ValueError("Invalid unresolved reference disposition")
    return document


def assess(
    case: dict[str, Any],
    observation: dict[str, Any],
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from detector_acceptance import evaluate

    document = load() if registry is None else registry
    errors = evaluate(case, observation)
    result: dict[str, Any] = {
        "ground_truth_status": "FAIL" if errors else "PASS",
        "ground_truth_errors": errors,
        "status": "REGRESSION" if errors else "REQUIRED_PASS",
        "blocking": bool(errors),
    }
    record = next(
        (r for r in document["records"] if r["fixture_id"] == case["fixture_id"]), None
    )
    if record is None:
        return result
    result.update(
        classification=record["classification"],
        risk=record["risk"],
        reason=record["reason"],
        approval=record["approval"],
        evidence=record["evidence"],
    )
    generator = (
        ROOT
        / "tools/generate_test_media"
        / ("audio.py" if case["fixture_id"].startswith("audio.") else "video.py")
    )
    bindings = {
        "case": digest(case) in record["case_sha256"],
        "generator": hashlib.sha256(generator.read_bytes()).hexdigest()
        == record["generator_sha256"],
        "profile": digest(observation.get("profile")) == record["profile_sha256"],
        "detectors": observation.get("detector_versions")
        == record["detector_versions"],
        "tools": digest(observation.get("provenance", {}).get("bundled_tools"))
        == record["tools_sha256"],
        "behavior": canonical(behavior(observation)) == canonical(record["behavior"]),
    }
    if observation["errors"] or any(
        observation["states"].get(d) != "COMPLETED" for d in case["detectors"]
    ):
        result.update(status="REGRESSION", blocking=True)
    elif not all(ok for key, ok in bindings.items() if key != "behavior") or not errors:
        result.update(
            status="REVIEW_REQUIRED",
            blocking=True,
            changed_bindings=[k for k, ok in bindings.items() if not ok],
        )
    elif not bindings["behavior"]:
        result.update(status="REGRESSION", blocking=True, changed_bindings=["behavior"])
    else:
        result.update(
            status="ACCEPTED_LIMITATION"
            if record["classification"] == "known_detector_limitation"
            else "ACCEPTED_EXPECTATION_LIMITATION",
            blocking=False,
        )
    return result


def report(results: list[dict[str, Any]]) -> dict[str, Any]:
    registry = load()
    for result in results:
        result["release"] = assess(
            result["expectations"], result["observation"], registry
        )
    exercised = {r["fixture_id"] for r in results}
    return {
        "results": results,
        "summary": {
            "ground_truth_failures": sum(
                r["release"]["ground_truth_status"] == "FAIL" for r in results
            ),
            "release_blockers": sum(r["release"]["blocking"] for r in results),
            "accepted_limitations": sum(
                r["release"]["status"].startswith("ACCEPTED_") for r in results
            ),
            "not_exercised": [
                r["fixture_id"]
                for r in registry["records"]
                if r["fixture_id"] not in exercised
            ],
        },
        "unresolved_references": registry["unresolved_references"],
    }
