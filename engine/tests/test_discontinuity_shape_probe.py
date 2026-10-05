"""Paired positive/negative challenge to the bounded isolation hypothesis."""

import json
from pathlib import Path

import numpy as np
import pytest
from discontinuity_shape_probe import candidates, interpolation_candidates
from generate_test_media.audio import RATE, transient_samples

from mediaqc_engine.detectors.audio.common import settings
from mediaqc_engine.detectors.audio.dsp import Regions
from mediaqc_engine.qc.profiles import builtin

MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "tests/fixtures/manifests/audio_discontinuity.json"
)
CASES = json.loads(MANIFEST.read_text())


def trial(
    kind: str, isolated: bool, interpolation: bool = False
) -> list[tuple[float, float]]:
    samples = transient_samples(kind)
    # Match 16-bit fixture quantization. This diagnostic holds only a synthetic
    # six-second fixture; candidate processing remains a bounded 20 ms window.
    samples = (samples * 32768).astype("<i2").astype(np.float64) / 32768
    previous = samples[0]
    region = Regions()
    events: list[tuple[float, float]] = []
    policy = settings(builtin(), "audio.discontinuity")
    for start in range(0, len(samples), 960):
        block = samples[start : start + 960]
        mask = candidates(block, previous, policy, isolated=isolated)
        if interpolation:
            following = (
                samples[start + len(block)]
                if start + len(block) < len(samples)
                else block[-1]
            )
            mask = interpolation_candidates(block, previous, following, policy)
        previous = block[-1]
        for index in np.flatnonzero(np.any(mask, axis=1)):
            time = (start + int(index)) / RATE
            closed = region.push(
                time, time + 1 / RATE, 0, float(str(policy["merge_gap_ms"])) / 1000
            )
            if closed:
                events.append(closed[:2])
    last = region.finish()
    if last:
        events.append(last[:2])
    return events


@pytest.mark.parametrize("case", CASES, ids=[c["fixture_id"] for c in CASES])
def test_isolation_hypothesis_and_recall_counterexamples(
    case: dict[str, object],
) -> None:
    kind = str(case["fixture_id"]).split(".")[2]
    # Container cases contain the same L/R constructions as these controls.
    kind = {"mxf_click": "simultaneous", "mxf_sharp": "sharp_stereo"}.get(kind, kind)
    observed = trial(kind, True)
    if kind in {"click_cluster", "wide_click"}:
        # A passing experiment test means the hypothesis is REJECTED, not that
        # these positives are clean. The production manifest still requires them.
        assert not observed
        assert trial(kind, False)
    else:
        expected = case["expected_findings"]
        assert isinstance(expected, list)
        unique = {(e["start_time_seconds"], e["end_time_seconds"]) for e in expected}
        assert len(observed) == len(unique)
        for actual, required in zip(observed, sorted(unique), strict=True):
            assert actual == pytest.approx(required, abs=1 / RATE)


@pytest.mark.parametrize("count,channels", [(961, 1), (0, 1), (960, 65)])
def test_shape_probe_is_bounded(count: int, channels: int) -> None:
    with pytest.raises(ValueError, match="bounded"):
        candidates(
            np.zeros((count, channels)),
            np.zeros(channels),
            settings(builtin(), "audio.discontinuity"),
            isolated=True,
        )


@pytest.mark.parametrize("case", CASES, ids=[c["fixture_id"] for c in CASES])
def test_interpolation_hypothesis_exposes_specificity_and_recall_limits(
    case: dict[str, object],
) -> None:
    kind = str(case["fixture_id"]).split(".")[2]
    kind = {"mxf_click": "simultaneous", "mxf_sharp": "sharp_stereo"}.get(kind, kind)
    events = trial(kind, False, interpolation=True)
    if kind in {"dc_step_moderate", "plateau_click"}:
        assert not events  # Rejection evidence; production manifest requires detection.
        assert trial(kind, False)
    elif kind == "sustained_shifted":
        assert events  # Remaining legitimate-content false positive.
    elif kind == "wide_click":
        assert events
        assert (
            events[0][1] < 2 + 3 / 48000
        )  # Event extent lost versus required end at +4 samples.
    else:
        expected = case["expected_findings"]
        assert isinstance(expected, list)
        unique = {(e["start_time_seconds"], e["end_time_seconds"]) for e in expected}
        assert len(events) == len(unique)
        for actual, required in zip(events, sorted(unique), strict=True):
            assert actual == pytest.approx(required, abs=1 / 48000)
