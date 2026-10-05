"""Acceptance oracle tests: wrong measurements and false positives must stay red."""

import copy
import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from detector_acceptance import (
    ROOT,
    artifact_path,
    evaluate,
    finding_errors,
    matches,
    numeric_match,
    run_case,
    validate_case,
)
from generate_test_media.video import frame
from reference_review import assess, overlap, replay_negatives, review_database

from mediaqc_engine.media.inspection import fingerprint
from mediaqc_engine.qc import profiles


def example() -> tuple[dict[str, Any], dict[str, Any]]:
    finding = {
        "detector_id": "audio.dropout",
        "stream_index": 2,
        "severity": "WARN",
        "start_time_seconds": 1.0,
        "end_time_seconds": 1.02,
    }
    case = {
        "fixture_id": "audio.dropout.short.001",
        "profile_version": "1.2.0",
        "detectors": ["audio.dropout"],
        "expected_findings": [{**finding, "timestamp_tolerance_seconds": 0.002}],
    }
    observation = {
        "findings": [finding],
        "metrics": [],
        "states": {"audio.dropout": "COMPLETED"},
        "errors": [],
    }
    return case, observation


@pytest.mark.parametrize(
    "field,value",
    [
        ("severity", "INFO"),
        ("stream_index", 1),
        ("end_time_seconds", 1.1),
        ("detector_id", "audio.discontinuity"),
        ("start_time_seconds", float("nan")),
    ],
)
def test_wrong_severity_stream_timestamp_or_detector_fails(
    field: str, value: object
) -> None:
    case, observation = example()
    assert not evaluate(case, observation)
    observation["findings"][0][field] = value
    assert evaluate(case, observation)


def test_extra_missing_and_disabled_execution_do_not_pass() -> None:
    case, observation = example()
    observation["findings"] *= 2
    assert evaluate(case, observation)
    observation["findings"] = []
    assert evaluate(case, observation)
    case["expected_findings"] = []
    for state in ("SKIPPED", "FAILED", "CANCELLED", None):
        observation["states"]["audio.dropout"] = state
        assert evaluate(case, observation)


def test_one_to_one_matching_handles_overlapping_tolerances() -> None:
    case, observation = example()
    exact = case["expected_findings"][0]
    broad = {**exact, "timestamp_tolerance_seconds": 0.5}
    shifted = {**observation["findings"][0], "start_time_seconds": 1.2}
    assert not finding_errors([observation["findings"][0], shifted], [broad, exact])
    assert finding_errors([shifted], [broad, exact])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "1", None])
def test_numeric_oracle_rejects_nonfinite_and_coerced_values(value: object) -> None:
    assert not numeric_match(value, 1, 1)
    assert not numeric_match(1, value, 1)
    assert not numeric_match(1, 1, value)


def test_metrics_null_state_and_forbidden_findings() -> None:
    case, observation = example()
    case["metric_expectations"] = [
        {
            "detector_id": "audio.dropout",
            "stream_index": 2,
            "metrics": {"candidate_count": {"value": 1, "abs_tolerance": 0}},
        }
    ]
    observation["metrics"] = [
        {
            "detector_id": "audio.dropout",
            "stream_index": 2,
            "metrics": {"candidate_count": 1},
        }
    ]
    assert not evaluate(case, observation)
    observation["metrics"][0]["metrics"]["candidate_count"] = 2
    assert evaluate(case, observation)
    assert not matches({}, {"integrated_lufs": None})
    assert matches(
        {"integrated_lufs": None, "state": "NO_GATED_AUDIO"},
        {"integrated_lufs": None, "state": "NO_GATED_AUDIO"},
    )
    case["forbidden_findings"] = [{"detector_id": "audio.dropout"}]
    assert any("Forbidden" in e for e in evaluate(case, observation))


@pytest.mark.parametrize(
    "mutation", ["typo", "severity", "tolerance", "scope", "profile"]
)
def test_manifest_rejects_ambiguous_or_invalid_expectations(mutation: str) -> None:
    case, _ = example()
    if mutation == "typo":
        case["expected_finding"] = []
    elif mutation == "severity":
        case["expected_findings"][0].pop("severity")
    elif mutation == "tolerance":
        case["expected_findings"][0]["timestamp_tolerance_seconds"] = -1
    elif mutation == "scope":
        case["detectors"] = ["audio.unknown"]
    else:
        case["profile_version"] = "latest"
    with pytest.raises(ValueError):
        validate_case(case)


def test_reference_review_never_suppresses_or_resolves_unknowns() -> None:
    _, observation = example()
    finding = {**observation["findings"][0], "id": "saved", "disposition": "OPEN"}
    reference: dict[str, Any] = {
        "negative_intervals": [
            {
                "intent": "normal camera behavior",
                "detectors": ["audio.dropout"],
                "start_time_seconds": 0,
                "end_time_seconds": 2,
            }
        ],
        "finding_reviews": {
            "saved": {"classification": "D", "reason": "Owner confirmed clean"}
        },
    }
    before = copy.deepcopy(finding)
    report = assess(reference, [finding], observation["states"])
    assert report["status"] == "FAIL" and finding == before
    reference["negative_intervals"] = []
    reference["finding_reviews"]["saved"]["classification"] = "C"
    assert assess(reference, [finding], observation["states"])["status"] == "UNRESOLVED"
    reference["finding_reviews"]["saved"]["classification"] = "B"
    assert assess(reference, [finding], observation["states"])["status"] == "REVIEWED"
    assert assess(reference, [], observation["states"])["status"] == "FAIL"


def test_unmeasured_negative_reference_cannot_pass() -> None:
    reference = {
        "negative_intervals": [
            {
                "intent": "zoom",
                "detectors": ["video.freeze"],
                "start_time_seconds": 1,
                "end_time_seconds": 3,
            }
        ]
    }
    assert assess(reference, [], {})["status"] == "FAIL"
    assert overlap(
        {"start_time_seconds": None, "end_time_seconds": None},
        reference["negative_intervals"][0],
    )


def test_output_cannot_target_source_or_tracked_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        artifact_path(tmp_path / "source.wav")
    with pytest.raises(ValueError):
        artifact_path(ROOT / "MASTER_SPEC.md")
    assert artifact_path(ROOT / ".cache" / "phase12" / "report.json")


def test_zoom_settling_gap_remains_visible_as_failed_acceptance(tmp_path: Path) -> None:
    # This asserts the diagnosis, not detector acceptance. The investigation CLI
    # must exit nonzero. Replace this with a clean acceptance assertion when fixed.
    case = json.loads(
        (ROOT / "tests/fixtures/manifests/investigation.json").read_text()
    )[0]
    assert not np.array_equal(frame(25, "zoom_settle"), frame(26, "zoom_settle"))
    result = run_case(case, tmp_path)
    assert result["status"] == "FAIL", (
        "Gap changed: re-evaluate and promote the negative case"
    )
    assert {f["detector_id"] for f in result["observation"]["findings"]} == {
        "video.duplicate_frame",
        "video.frame_cadence",
    }


def test_current_profile_document_is_unchanged() -> None:
    # Pinned before Phase 12 implementation; changing policy requires separate review.
    import hashlib

    profile = ROOT / "engine/src/mediaqc_engine/qc/general_technical_qc.json"
    canonical = json.dumps(
        json.loads(profile.read_text()), sort_keys=True, separators=(",", ":")
    )
    assert (
        hashlib.sha256(canonical.encode()).hexdigest()
        == "19aabeaa29aedd58c0ebc81d302a21d78463217fc94840b5698d6d65efd5643b"
    )


def test_every_detector_has_manifest_positive_and_scoped_control() -> None:
    from detector_acceptance import REGISTRY

    cases = []
    for name in ("audio", "video"):
        cases.extend(
            json.loads((ROOT / f"tests/fixtures/manifests/{name}.json").read_text())
        )
    positive = {f["detector_id"] for case in cases for f in case["expected_findings"]}
    assert positive == set(REGISTRY)
    for case in cases:
        validate_case(case)


def test_reference_database_is_read_only_and_identity_checked(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"local identity fixture")
    database = tmp_path / "project.sqlite"
    identity = fingerprint(source)["fast_fingerprint_sha256"]
    profile = profiles.builtin()
    with sqlite3.connect(database) as db:
        db.executescript("""
            CREATE TABLE media_assets(id TEXT, absolute_path TEXT, file_name TEXT);
            CREATE TABLE analysis_runs(id TEXT, media_asset_id TEXT, status TEXT,
              ai_mode TEXT, media_fingerprint_sha256 TEXT,
              qc_profile_snapshot_json TEXT, overall_result TEXT);
            CREATE TABLE media_streams(id TEXT, stream_index INTEGER);
            CREATE TABLE findings(id TEXT, analysis_run_id TEXT, detector_id TEXT,
              stream_id TEXT, measurements_json TEXT, threshold_json TEXT,
              metadata_json TEXT);
            CREATE TABLE detector_executions(analysis_run_id TEXT, detector_id TEXT,
              detector_version TEXT, status TEXT, metrics_json TEXT);
        """)
        db.execute(
            "INSERT INTO media_assets VALUES (?,?,?)",
            ("asset", str(source), source.name),
        )
        db.execute(
            "INSERT INTO analysis_runs VALUES (?,?,?,?,?,?,?)",
            ("run", "asset", "COMPLETED", "OFF", identity, json.dumps(profile), "PASS"),
        )
    before = database.read_bytes(), source.read_bytes(), source.stat().st_mtime_ns
    reference = {
        "reference_id": "local",
        "run_id": "run",
        "source": str(source),
        "fast_fingerprint_sha256": identity,
        "assignments": {"expected_silence": True},
    }
    manifest = {
        "schema_version": "1.0.0",
        "ai_mode": "OFF",
        "database": str(database),
        "profile_snapshot": profile,
        "references": [reference],
    }
    result = review_database(manifest)
    assert result["references"][0]["status"] == "REVIEWED"
    assert before == (
        database.read_bytes(),
        source.read_bytes(),
        source.stat().st_mtime_ns,
    )
    source.write_bytes(b"changed source")
    with pytest.raises(ValueError, match="changed"):
        review_database(manifest)


def test_fresh_replay_ignores_saved_dispositions(tmp_path: Path) -> None:
    from unittest.mock import patch

    reference = {
        "reference_id": "local",
        "source": str(tmp_path / "source.mp4"),
        "fast_fingerprint_sha256": "identity",
        "finding_reviews": {},
        "negative_intervals": [
            {
                "intent": "zoom",
                "detectors": ["video.frame_cadence"],
                "start_time_seconds": 1,
                "end_time_seconds": 3,
            }
        ],
    }
    observation = {
        "profile": profiles.builtin(),
        "errors": [],
        "states": {"video.frame_cadence": "COMPLETED"},
        "findings": [
            {
                "detector_id": "video.frame_cadence",
                "start_time_seconds": 2,
                "end_time_seconds": 2.1,
                "disposition": "IGNORED",
            }
        ],
    }
    manifest = {"references": [reference], "profile_snapshot": profiles.builtin()}
    with (
        patch(
            "reference_review.fingerprint",
            return_value={"fast_fingerprint_sha256": "identity"},
        ),
        patch("reference_review.observe", return_value=observation),
    ):
        assert replay_negatives(manifest, tmp_path)[0]["status"] == "FAIL"
        observation["findings"] = []
        assert replay_negatives(manifest, tmp_path)[0]["status"] == "PASS"
