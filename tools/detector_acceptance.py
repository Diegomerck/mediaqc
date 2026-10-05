"""Developer-only deterministic corpus runner; never changes runtime QC policy."""

import argparse
import hashlib
import json
import logging
import math
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

from generate_test_media.audio import generate as audio_fixture
from generate_test_media.video import generate as video_fixture

from mediaqc_engine.detectors.audio import registry as audio_registry
from mediaqc_engine.detectors.audio.pcm import cleanup
from mediaqc_engine.detectors.common import settings
from mediaqc_engine.detectors.contract import DetectorContext
from mediaqc_engine.detectors.video import registry as video_registry
from mediaqc_engine.jobs.cancellation import CancellationToken
from mediaqc_engine.media.inspection import map_probe
from mediaqc_engine.media.tools import MediaTools, tool_directory
from mediaqc_engine.qc import profiles

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = {d.detector_id: d for d in (*audio_registry(), *video_registry())}
type Document = dict[str, Any]


def artifact_path(path: Path) -> Path:
    resolved = path.resolve()
    if not any(
        resolved.is_relative_to((ROOT / root).resolve())
        for root in (".cache", "tests/fixtures/generated")
    ):
        raise ValueError(
            "Acceptance outputs must be in ignored cache/generated directories"
        )
    return resolved


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def provenance() -> Document:
    files = list((ROOT / "engine/src/mediaqc_engine/detectors").rglob("*.py"))
    files += list((ROOT / "tools/generate_test_media").glob("*.py"))
    files += [Path(__file__), ROOT / "uv.lock"]
    return {
        "python": sys.version,
        "bundled_tools": json.loads((tool_directory() / "provenance.json").read_text()),
        "code_sha256": {str(p.relative_to(ROOT)): digest(p) for p in files},
    }


def numeric_match(actual: object, expected: object, tolerance: object) -> bool:
    if any(
        isinstance(x, bool) or not isinstance(x, (int, float))
        for x in (actual, expected, tolerance)
    ):
        return False
    a, b, t = float(str(actual)), float(str(expected)), float(str(tolerance))
    return (
        all(math.isfinite(x) for x in (a, b, t)) and t >= 0 and abs(a - b) <= t + 1e-12
    )


def matches(actual: Document, expected: Document) -> bool:
    for key, value in expected.items():
        if key == "timestamp_tolerance_seconds":
            continue
        observed = actual.get(key)
        if key in {"start_time_seconds", "end_time_seconds"} and value is not None:
            if not numeric_match(
                observed, value, expected["timestamp_tolerance_seconds"]
            ):
                return False
        elif isinstance(value, dict):
            if set(value) == {"value", "abs_tolerance"}:
                if not numeric_match(observed, value["value"], value["abs_tolerance"]):
                    return False
            elif not isinstance(observed, dict) or not matches(observed, value):
                return False
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            if not numeric_match(observed, value, 0):
                return False
        elif key not in actual or observed != value:
            return False
    return True


def finding_errors(actual: list[Document], expected: list[Document]) -> list[str]:
    """One-to-one matching; overlapping tolerance windows cannot hide extra events."""
    owners: dict[int, int] = {}

    def assign(index: int, visited: set[int]) -> bool:
        for candidate, finding in enumerate(actual):
            if candidate in visited or not matches(finding, expected[index]):
                continue
            visited.add(candidate)
            if candidate not in owners or assign(owners[candidate], visited):
                owners[candidate] = index
                return True
        return False

    errors = []
    for index, expectation in enumerate(expected):
        if not assign(index, set()):
            errors.append(f"Missing/mismatched finding: {expectation}")
    for index, finding in enumerate(actual):
        if index not in owners:
            errors.append(
                f"Unexpected finding: {finding['detector_id']} "
                f"stream={finding.get('stream_index')} "
                f"at={finding.get('start_time_seconds')}"
            )
    return errors


def validate_case(case: Document) -> None:
    json.dumps(case, allow_nan=False)
    if not re.fullmatch(r"[a-z0-9_.]+", str(case.get("fixture_id", ""))):
        raise ValueError("Fixture ID must be a simple stable identifier")
    allowed = {
        "fixture_id",
        "generator_version",
        "file",
        "duration_seconds",
        "parameters",
        "expected_findings",
        "forbidden_findings",
        "detectors",
        "profile_version",
        "profile_overrides",
        "metric_expectations",
        "rationale",
        "category",
    }
    if case.keys() - allowed:
        raise ValueError(f"Unknown manifest fields: {case.keys() - allowed}")
    if not case.get("fixture_id") or case.get("profile_version") != "1.2.0":
        raise ValueError("A fixture ID and explicit profile_version 1.2.0 are required")
    scope = case.get("detectors")
    if not isinstance(scope, list) or not scope or len(set(scope)) != len(scope):
        raise ValueError("Explicit nonempty unique detector scope is required")
    if set(scope) - REGISTRY.keys():
        raise ValueError("Unknown detector ID")
    if not isinstance(case.get("expected_findings"), list):
        raise ValueError("Expected findings must be explicit, including an empty list")
    for item in case["expected_findings"]:
        allowed_finding = {
            "detector_id",
            "severity",
            "stream_index",
            "start_time_seconds",
            "end_time_seconds",
            "timestamp_tolerance_seconds",
            "measurements",
        }
        if item.keys() - allowed_finding or item.get("detector_id") not in scope:
            raise ValueError("Invalid finding fields or detector outside scope")
        if item.get("severity") not in {"INFO", "WARN", "FAIL"}:
            raise ValueError("Exact finding severity is required")
        stream_index = item.get("stream_index")
        if type(stream_index) is not int or stream_index < 0:
            raise ValueError("Explicit nonnegative stream index is required")
        if any(
            item.get(k) is not None for k in ("start_time_seconds", "end_time_seconds")
        ):
            tolerance = item.get("timestamp_tolerance_seconds")
            if not numeric_match(tolerance, tolerance, 0) or tolerance < 0:
                raise ValueError("Finite nonnegative timestamp tolerance is required")
    for item in case.get("forbidden_findings", []):
        if (
            item.keys() - {"detector_id", "stream_index"}
            or item.get("detector_id") not in scope
        ):
            raise ValueError("Forbidden detector outside scope")
    for item in case.get("metric_expectations", []):
        if item.get("detector_id") not in scope or "stream_index" not in item:
            raise ValueError("Metrics need an in-scope detector and stream index")
    if set(case.get("profile_overrides", {})) - set(scope):
        raise ValueError("Profile override outside detector scope")


def evaluate(case: Document, observation: Document) -> list[str]:
    validate_case(case)
    errors = list(observation.get("errors", []))
    for detector in case["detectors"]:
        if observation["states"].get(detector) != "COMPLETED":
            errors.append(f"{detector}: did not complete")
    actual = observation["findings"]
    errors.extend(finding_errors(actual, case["expected_findings"]))
    for forbidden in case.get("forbidden_findings", []):
        if any(matches(f, forbidden) for f in actual):
            errors.append(f"Forbidden finding: {forbidden}")
    for expectation in case.get("metric_expectations", []):
        if not any(matches(m, expectation) for m in observation["metrics"]):
            errors.append(f"Missing/mismatched metric: {expectation}")
    return errors


def observe(source: Path, case: Document, work: Path) -> Document:
    """Use real decode/probe metadata, exact source bytes and bounded engine caches."""
    validate_case(case)
    profile = profiles.builtin(case["profile_version"])
    for detector, patch in case.get("profile_overrides", {}).items():
        settings(profile, detector).update(patch)
    profiles.validate(profile)
    before = digest(source), source.stat().st_size, source.stat().st_mtime_ns
    token = CancellationToken()
    tools = MediaTools(cancellation=token.event, cache=work)
    result: Document = {
        "findings": [],
        "metrics": [],
        "states": {},
        "errors": [],
        "warnings": {},
        "profile": profile,
        "source_sha256": before[0],
        "ai_mode": "OFF",
        "provenance": provenance(),
        "detector_versions": {
            d: REGISTRY[d].detector_version for d in case["detectors"]
        },
    }
    try:
        metadata, streams = map_probe(tools.probe(source))
        streams = [{**s, "id": str(s["stream_index"])} for s in streams]
        context = DetectorContext(
            "acceptance",
            {**metadata, "absolute_path": str(source)},
            tuple(streams),
            profile,
            str(work),
            token,
            tools,
            logging.LoggerAdapter(logging.getLogger(__name__), {}),
        )
        for identifier in case["detectors"]:
            detector = REGISTRY[identifier]
            if not settings(profile, identifier)["enabled"] or not detector.supports(
                context
            ):
                result["states"][identifier] = "SKIPPED"
                continue
            try:
                measured = detector.analyze(context)
                result["states"][identifier] = "COMPLETED"
                result["warnings"][identifier] = measured.warnings
                for finding in measured.findings:
                    if finding.get("threshold") != settings(profile, identifier):
                        result["errors"].append(
                            f"{identifier}: finding policy differs from snapshot"
                        )
                    if finding.get("detector_version") != detector.detector_version:
                        result["errors"].append(
                            f"{identifier}: finding version differs from registry"
                        )
                    if finding.get("stream_id") not in {s["id"] for s in streams}:
                        raise ValueError("Finding references an unknown stream")
                    result["findings"].append(
                        {**finding, "stream_index": int(str(finding["stream_id"]))}
                    )
                for stream_id, metrics in cast(
                    Document, measured.metrics.get("streams", {})
                ).items():
                    result["metrics"].append(
                        {
                            "detector_id": identifier,
                            "stream_index": int(stream_id),
                            "metrics": metrics,
                        }
                    )
            except Exception as exc:
                result["states"][identifier] = "FAILED"
                result["errors"].append(f"{identifier}: {type(exc).__name__}: {exc}")
    finally:
        tools.cancel()
        cleanup(work)
        after = digest(source), source.stat().st_size, source.stat().st_mtime_ns
        if before != after:
            raise AssertionError("Source changed during acceptance")
    return result


def run_case(case: Document, directory: Path) -> Document:
    validate_case(case)
    generator = (
        audio_fixture if case["fixture_id"].startswith("audio.") else video_fixture
    )
    source = generator(case["fixture_id"], directory / "source")
    if "file" in case and source.name != case["file"]:
        raise ValueError("Generated filename differs from manifest")
    observation = observe(source, case, directory / "cache")
    errors = evaluate(case, observation)
    return {
        "fixture_id": case["fixture_id"],
        "generator_version": case["generator_version"],
        "expectations": case,
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "observation": observation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--release",
        action="store_true",
        help="Report approved V1 dispositions separately from ground truth",
    )
    args = parser.parse_args()
    output = artifact_path(args.output)
    cache = ROOT / ".cache" / "phase12"
    cache.mkdir(parents=True, exist_ok=True)
    results = []
    for case in (
        case
        for manifest in args.manifest
        for case in json.loads(manifest.read_text(encoding="utf-8"))
    ):
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            results.append(run_case(case, Path(temporary)))
        print(case["fixture_id"], results[-1]["status"])
    output.parent.mkdir(parents=True, exist_ok=True)
    from acceptance_disposition import report

    payload = report(results) if args.release else results
    output.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    if args.release:
        assert isinstance(payload, dict)
        for result in results:
            print(
                result["fixture_id"],
                result["release"]["status"],
                "ground truth",
                result["status"],
            )
        print("Release summary:", json.dumps(payload["summary"], sort_keys=True))
        print(
            "Unresolved references:",
            json.dumps(payload["unresolved_references"], sort_keys=True),
        )
        return int(any(r["release"]["blocking"] for r in results))
    return int(any(r["status"] != "PASS" for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
