"""Phase 12 audio gates; ground-truth gaps and release dispositions stay separate."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest
from acceptance_disposition import assess
from audio_reference_probe import program_loudness, transient_metrics
from detector_acceptance import ROOT, digest, run_case
from generate_test_media.audio import RATE, generate, transient_samples

from mediaqc_engine.detectors.audio.levels import LevelDetector
from mediaqc_engine.detectors.contract import DetectorContext
from mediaqc_engine.media.tools import MediaTools
from mediaqc_engine.qc.profiles import builtin

CASES = [
    case
    for manifest in ("audio_discontinuity.json", "audio_applicability.json")
    for case in json.loads((ROOT / "tests/fixtures/manifests" / manifest).read_text())
]


@pytest.mark.parametrize("case", CASES, ids=[c["fixture_id"] for c in CASES])
def test_audio_calibration_manifest(tmp_path: Path, case: dict[str, Any]) -> None:
    result = run_case(case, tmp_path)
    result["release"] = assess(case, result["observation"])
    (tmp_path / "acceptance.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    assert not result["release"]["blocking"], result


def test_simultaneity_is_not_a_defect_or_clean_label() -> None:
    for kind in ("simultaneous", "sharp_stereo"):
        samples = transient_samples(kind)
        assert np.array_equal(samples[:, 0], samples[:, 1])
        measured = transient_metrics(samples[2 * RATE - 960 : 2 * RATE + 7680, 0])
        assert any(
            w["candidate_sample_count"]
            for w in cast(list[dict[str, Any]], measured["windows"])
        )


def test_legitimate_sharp_onset_is_continuous_and_not_clipped() -> None:
    def onset(t: float) -> float:
        t = max(t, 0)
        return float(
            0.8
            * (1 - np.exp(-t / 0.0001))
            * np.exp(-t / 0.0008)
            * np.sin(2 * np.pi * 8000 * t)
        )

    assert onset(-1e-9) == onset(0) == 0
    assert abs(onset(1e-9)) < 1e-9
    assert np.max(np.abs(transient_samples("sharp"))) < 1


def test_channel_intent_does_not_change_silence_measurement(tmp_path: Path) -> None:
    unused = generate("audio.unused_iso.001", tmp_path)
    required = generate("audio.required_silent.001", tmp_path)
    assert unused.read_bytes() == required.read_bytes()


def test_explicit_lr_program_excludes_iso_channels(tmp_path: Path) -> None:
    mono = generate("audio.clean.001", tmp_path)
    multi = generate("audio.production_multitrack.001", tmp_path)
    before = digest(mono), digest(multi)
    tools = MediaTools(cache=tmp_path / "metadata")
    try:
        single = program_loudness(tools, mono, "[0:0]asetpts=PTS-STARTPTS")
        program = program_loudness(
            tools, multi, "[0:0]pan=stereo|c0=c0|c1=c1,asetpts=PTS-STARTPTS"
        )
        # Two equal full-length channels double the K-weighted energy; the five
        # additional ISOs must not contribute to the selected program.
        assert program["I"] - single["I"] == pytest.approx(10 * np.log10(2), abs=0.002)
    finally:
        tools.cancel()
        assert not tools.pids
        assert before == (digest(mono), digest(multi))


@pytest.mark.parametrize("count", [959, RATE // 2 + 1])
def test_reference_probe_requires_bounded_context(count: int) -> None:
    with pytest.raises(ValueError, match="20-500 ms"):
        transient_metrics(np.zeros(count))


@pytest.mark.parametrize("rounded", [False, True])
def test_required_silence_is_not_exempted_by_duration_rounding(
    monkeypatch: pytest.MonkeyPatch, rounded: bool
) -> None:
    count = 100001
    seconds = count / RATE
    stream = {
        "id": "required",
        "channel_count": 1,
        "duration_seconds": round(seconds, 6) if rounded else seconds,
    }
    context = cast(
        DetectorContext, SimpleNamespace(qc_profile=builtin(), media_asset={})
    )
    samples = np.broadcast_to(np.zeros((1, 1)), (count, 1))
    monkeypatch.setattr(
        "mediaqc_engine.detectors.audio.levels.windows",
        lambda *_: iter([(0, samples, RATE)]),
    )
    result = LevelDetector("audio.silence").measure(context, stream)
    assert len(result.findings) == 1  # ignore_tail_seconds=0 must not exempt EOF.
    assert result.findings[0]["end_time_seconds"] == pytest.approx(seconds)


@pytest.mark.parametrize("assigned", [False, True])
@pytest.mark.parametrize(
    "declared,asset,tail,head,start,count,amplitude,expected",
    [
        (2.083354, 0, 0, 0, 0, 100001, 0, 1),
        (2.083355, 0, 0, 0, 0, 100001, 0, 1),
        (None, 2.083354, 0, 0, 0, 100001, 0, 1),
        (None, 0, 0, 0, 0, 100001, 0, 1),
        (2.083354, 0, 0.01, 0, 0, 100001, 0, 0),
        (3, 0, 1, 0, 0, 96000, 0, 1),
        (3, 0, 1, 0, 0, 96001, 0, 0),
        (3, 0, 0, 0.01, 0, 96000, 0, 0),
        (3, 0, 0, 0.01, 0.01, 96000, 0, 1),
        (2, 0, 0, 0, 0, 95999, 0, 0),
        (2, 0, 0, 0, 0, 96000, 0, 1),
        (2.083354, 0, 0, 0, 0, 100001, 0.1, 0),
    ],
)
def test_silence_edge_contract(
    monkeypatch: pytest.MonkeyPatch,
    assigned: bool,
    declared: float | None,
    asset: float,
    tail: float,
    head: float,
    start: float,
    count: int,
    amplitude: float,
    expected: int,
) -> None:
    from mediaqc_engine.detectors.audio.common import settings

    profile = builtin()
    settings(profile, "audio.silence").update(
        ignore_tail_seconds=tail, ignore_head_seconds=head
    )
    from mediaqc_engine.qc.audio_applicability import parse_contract

    assignment = (
        parse_contract(
            {
                "schema_version": "0.1.0",
                "source_sha256": "a" * 64,
                "provenance": "boundary-test",
                "channels": [
                    {"member": [0, 0], "role": "iso", "expectation": "expected"}
                ],
                "programs": [],
            },
            {0: 1},
            "a" * 64,
        )
        if assigned
        else None
    )
    context = cast(
        DetectorContext,
        SimpleNamespace(
            qc_profile=profile,
            media_asset={"duration_seconds": asset},
            audio_assignment=assignment,
        ),
    )
    stream = {
        "id": "required",
        "stream_index": 0,
        "channel_count": 1,
        "duration_seconds": declared,
    }
    samples = np.broadcast_to(np.full((1, 1), amplitude), (count, 1))
    monkeypatch.setattr(
        "mediaqc_engine.detectors.audio.levels.windows",
        lambda *_: iter([(start, samples, RATE)]),
    )
    result = LevelDetector("audio.silence").measure(context, stream)
    assert len(result.findings) == expected
    assert result.metrics["sample_count_per_channel"] == count
    assert result.metrics["decoded_duration_seconds"] == start + count / RATE
    if expected:
        assert result.findings[0]["severity"] == "WARN"
        assert result.findings[0]["end_time_seconds"] == start + count / RATE


@pytest.mark.parametrize("kind", ["masked", "sharp_busy"])
def test_per_channel_baseline_alone_is_not_a_safe_correction(kind: str) -> None:
    from mediaqc_engine.detectors.audio.common import number, settings

    samples = transient_samples(kind)[2 * RATE - 1 : 2 * RATE + 960]
    derivative = np.abs(np.diff(samples, axis=0))
    policy = settings(builtin(), "audio.discontinuity")
    scale = 2 - number(policy, "sensitivity")
    amplitude = number(policy, "min_jump_amplitude") * scale
    ratio = number(policy, "min_derivative_ratio") * scale
    shared = np.max(derivative, axis=1)
    assert not np.any((shared >= amplitude) & (shared / np.median(shared) >= ratio))
    per_channel = derivative / np.maximum(np.median(derivative, axis=0), 1e-12)
    # The proposed baseline change recovers the click but also unmasks the
    # legitimate sharp sound. It cannot alone satisfy both acceptance labels.
    assert np.any((derivative >= amplitude) & (per_channel >= ratio))


def test_audio_algorithm_versions() -> None:
    from mediaqc_engine.detectors.audio import registry

    for detector in registry():
        assert detector.detector_version == (
            "1.1.0"
            if detector.detector_id == "audio.silence"
            or detector.detector_id.startswith("audio.loudness.")
            else "1.0.0"
        )


def test_explicit_cross_stream_program_matches_stereo(tmp_path: Path) -> None:
    stereo = generate("audio.discontinuity.simultaneous.001", tmp_path)
    mxf = generate("audio.discontinuity.mxf_click.001", tmp_path)
    before = digest(stereo), digest(mxf)
    tools = MediaTools(cache=tmp_path / "metadata")
    try:
        expected = program_loudness(tools, stereo, "[0:0]asetpts=PTS-STARTPTS")
        actual = program_loudness(
            tools,
            mxf,
            "[0:1][0:2]join=inputs=2:channel_layout=stereo:map=0.0-FL|1.0-FR,"
            "asetpts=PTS-STARTPTS",
        )
        assert actual["I"] == pytest.approx(expected["I"], abs=0.002)
    finally:
        tools.cancel()
        assert not tools.pids
        assert before == (digest(stereo), digest(mxf))
