"""Exact approved exceptions never waive ground truth or unexpected regressions."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from acceptance_disposition import assess, behavior, load, report
from detector_acceptance import ROOT, run_case

from mediaqc_engine.media.tools import tool_directory
from mediaqc_engine.qc.profiles import builtin

NAMES = {
    "audio.discontinuity." + name + ".001"
    for name in (
        "masked",
        "masked_swapped",
        "sharp",
        "sharp_stereo",
        "sharp_delayed",
        "sustained_shifted",
        "mxf_sharp",
    )
} | {
    "video." + name + ".001"
    for name in (
        "zoom_settle",
        "static_between_cuts",
        "intentional_hold",
        "intentional_hold_lossy",
        "intentional_periodic_hold",
    )
}


def cases() -> dict[str, Any]:
    return {
        c["fixture_id"]: c
        for name in ("audio_discontinuity", "video_repeats", "video_temporal_context")
        for c in json.loads(
            (ROOT / f"tests/fixtures/manifests/{name}.json").read_text()
        )
    }


def example(
    identifier: str = "audio.discontinuity.masked.001",
) -> tuple[dict[str, Any], dict[str, Any]]:
    record = next(r for r in load()["records"] if r["fixture_id"] == identifier)
    observation = copy.deepcopy(record["behavior"])
    observation.update(
        profile=builtin(),
        detector_versions=record["detector_versions"],
        provenance={
            "bundled_tools": json.loads(
                (tool_directory() / "provenance.json").read_text()
            )
        },
    )
    return cases()[identifier], observation


def test_registry_inventory_and_unresolved_reference_are_explicit() -> None:
    document = load()
    assert {r["fixture_id"] for r in document["records"]} == NAMES
    assert sum(r["risk"] == "missed_defect" for r in document["records"]) == 2
    assert (
        sum(
            r["classification"] == "acceptance_expectation_problem"
            for r in document["records"]
        )
        == 3
    )
    unresolved = document["unresolved_references"][0]
    assert unresolved["status"] == "NEEDS_INDEPENDENT_EVIDENCE"
    assert not unresolved["blocking"]
    assert unresolved["reference_id"] not in NAMES


@pytest.mark.parametrize("identifier", sorted(NAMES))
def test_bound_behavior_retains_ground_truth_failure(identifier: str) -> None:
    case, observation = example(identifier)
    before = copy.deepcopy((case, observation))
    assessment = assess(case, observation)
    assert assessment["ground_truth_status"] == "FAIL"
    assert assessment["ground_truth_errors"]
    assert assessment["status"].startswith("ACCEPTED_")
    assert assessment["blocking"] is False
    assert (case, observation) == before


@pytest.mark.parametrize(
    "mutation",
    [
        "fixture",
        "annotation",
        "generator_version",
        "detector_scope",
        "threshold",
        "profile_version",
        "detector_version",
        "tools",
        "missing_metrics",
        "new_metric",
        "extra_finding",
        "failed",
        "skipped",
        "error",
        "warning",
        "severity",
        "stream",
        "time",
        "measurement",
        "improvement",
        "generator_source",
    ],
)
def test_changes_cannot_inherit_an_exception(mutation: str) -> None:
    case, observation = example("audio.discontinuity.sharp.001")
    registry = load()
    if mutation == "fixture":
        case["fixture_id"] = "audio.discontinuity.unapproved.001"
    elif mutation == "annotation":
        case["rationale"] += " changed intent"
    elif mutation == "generator_version":
        case["generator_version"] = "99.0.0"
    elif mutation == "detector_scope":
        case["detectors"].append("audio.silence")
        observation["states"]["audio.silence"] = "COMPLETED"
    elif mutation == "threshold":
        observation["profile"]["audio"]["discontinuity"]["min_jump_amplitude"] = 0.001
    elif mutation == "profile_version":
        observation["profile"]["version"] = "99.0.0"
    elif mutation == "detector_version":
        observation["detector_versions"]["audio.discontinuity"] = "99.0.0"
    elif mutation == "tools":
        observation["provenance"]["bundled_tools"] = {}
    elif mutation == "missing_metrics":
        observation["metrics"] = []
    elif mutation == "new_metric":
        observation["metrics"][0]["metrics"]["new"] = 1
    elif mutation == "extra_finding":
        observation["findings"] *= 2
    elif mutation in ("failed", "skipped"):
        observation["states"]["audio.discontinuity"] = mutation.upper()
    elif mutation == "error":
        observation["errors"].append("decode failed")
    elif mutation == "warning":
        observation["warnings"]["audio.discontinuity"].append({"code": "NEW"})
    elif mutation == "severity":
        observation["findings"][0]["severity"] = "FAIL"
    elif mutation == "stream":
        observation["findings"][0]["stream_index"] = 4
    elif mutation == "time":
        observation["findings"][0]["start_time_seconds"] += 1 / 48000
    elif mutation == "measurement":
        observation["findings"][0]["measurements"]["derivative_ratio"] += 0.01
    elif mutation == "improvement":
        observation["findings"] = []
    else:
        for record in registry["records"]:
            record["generator_sha256"] = "0" * 64
    result = assess(case, observation, registry)
    assert result["blocking"]
    assert not result["status"].startswith("ACCEPTED_")


def test_unregistered_missed_defect_and_clean_control_remain_required() -> None:
    case, observation = example()
    case["fixture_id"] = "audio.discontinuity.new_masked.001"
    assert assess(case, observation)["status"] == "REGRESSION"
    case["expected_findings"] = []
    assert assess(case, observation)["status"] == "REQUIRED_PASS"


@pytest.mark.parametrize(
    "mutation",
    ["duplicate", "extra_field", "failed_baseline", "oversize", "unresolved_clean"],
)
def test_invalid_registry_fails_closed(tmp_path: Path, mutation: str) -> None:
    document = load()
    if mutation == "duplicate":
        document["records"].append(document["records"][0])
    elif mutation == "extra_field":
        document["records"][0]["allow_any_finding"] = True
    elif mutation == "failed_baseline":
        document["records"][0]["behavior"]["errors"] = ["failure"]
    elif mutation == "unresolved_clean":
        document["unresolved_references"][0]["status"] = "CLEAN"
    path = tmp_path / "registry.json"
    path.write_text(
        " " * (1024 * 1024 + 1) if mutation == "oversize" else json.dumps(document)
    )
    with pytest.raises(ValueError):
        load(path)


def test_report_exposes_failures_and_unexercised_cases() -> None:
    case, observation = example()
    results = [
        {
            "fixture_id": case["fixture_id"],
            "expectations": case,
            "observation": observation,
            "status": "FAIL",
            "errors": ["missed click"],
        }
    ]
    output = report(results)
    assert output["summary"]["ground_truth_failures"] == 1
    assert output["summary"]["accepted_limitations"] == 1
    assert output["summary"]["release_blockers"] == 0
    assert len(output["summary"]["not_exercised"]) == 11
    assert results[0]["status"] == "FAIL" and results[0]["errors"] == ["missed click"]
    assert output["unresolved_references"]


@pytest.mark.parametrize(
    "negative,positive",
    [
        ("intentional_hold", "single_duplicate"),
        ("intentional_hold_lossy", "single_duplicate_lossy"),
        ("intentional_periodic_hold", "broken_cadence"),
    ],
)
def test_identical_inputs_require_identical_detector_observations(
    tmp_path: Path, negative: str, positive: str
) -> None:
    corpus = cases()
    clean = run_case(corpus[f"video.{negative}.001"], tmp_path / "authored")
    fault = run_case(corpus[f"video.{positive}.001"], tmp_path / "fault")
    assert (
        clean["observation"]["source_sha256"] == fault["observation"]["source_sha256"]
    )
    assert behavior(clean["observation"]) == behavior(fault["observation"])
    assert clean["status"] == "FAIL" and fault["status"] == "PASS"
    assert not assess(clean["expectations"], clean["observation"])["blocking"]
    assert (
        assess(fault["expectations"], fault["observation"])["status"] == "REQUIRED_PASS"
    )


@pytest.mark.parametrize("release", [False, True])
def test_cli_exit_and_report_preserve_ground_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    release: bool,
) -> None:
    import sys

    import detector_acceptance

    case, observation = example()
    manifest = tmp_path / "cases.json"
    manifest.write_text(json.dumps([case]))
    output = tmp_path / "report.json"
    monkeypatch.setattr(detector_acceptance, "artifact_path", lambda path: path)
    monkeypatch.setattr(
        detector_acceptance,
        "run_case",
        lambda *_: {
            "fixture_id": case["fixture_id"],
            "expectations": case,
            "observation": observation,
            "status": "FAIL",
            "errors": ["missed click"],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["acceptance", str(manifest), "--output", str(output)]
        + (["--release"] if release else []),
    )
    assert detector_acceptance.main() == (0 if release else 1)
    saved = json.loads(output.read_text())
    rows = saved["results"] if release else saved
    assert rows[0]["status"] == "FAIL"
    assert rows[0]["errors"] == ["missed click"]
    console = capsys.readouterr().out
    assert "FAIL" in console
    if release:
        assert "ACCEPTED_LIMITATION" in console
        assert "NEEDS_INDEPENDENT_EVIDENCE" in console
        assert saved["summary"]["ground_truth_failures"] == 1


def test_uuid_and_order_are_the_only_ignored_finding_fields() -> None:
    case, observation = example("audio.discontinuity.mxf_sharp.001")
    for item in observation["findings"]:
        item["id"] = "new-run-uuid"
    observation["findings"].reverse()
    observation["metrics"].reverse()
    assert not assess(case, observation)["blocking"]
    observation["findings"][0]["confidence"] = None
    assert assess(case, observation)["blocking"]
