"""Temporal discrimination acceptance and identifiability counterexamples.

Negative ground truth remains negative even where source-only inference cannot
distinguish it from a fault. Those ground-truth failures remain visible beside
approved release dispositions.
"""

import hashlib
import json
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from acceptance_disposition import assess
from detector_acceptance import ROOT, evaluate, run_case
from generate_test_media.video import FPS, frame
from repeat_temporal_probe import MAX_FRAMES, probe, temporal_features

CASES = json.loads(
    (ROOT / "tests/fixtures/manifests/video_temporal_context.json").read_text()
)


@pytest.mark.parametrize("case", CASES, ids=[c["fixture_id"] for c in CASES])
def test_temporal_acceptance(tmp_path: Path, case: dict[str, Any]) -> None:
    result = run_case(case, tmp_path)
    result["release"] = assess(case, result["observation"])
    (tmp_path / "acceptance.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    assert not result["release"]["blocking"], result


@pytest.mark.parametrize(
    "intentional,defect",
    [
        ("intentional_hold", "single_duplicate"),
        ("intentional_hold_lossy", "single_duplicate_lossy"),
        ("intentional_periodic_hold", "broken_cadence"),
    ],
)
def test_full_temporal_observations_cannot_identify_intent(
    intentional: str, defect: str
) -> None:
    # Compare every source image AND presentation time, not just the candidate
    # pair. The generator applies identical encoding settings to each pair.
    clean, faulty = hashlib.sha256(), hashlib.sha256()
    for index in range(100):
        pts = str(index / FPS).encode()
        clean.update(pts + frame(index, intentional).tobytes())
        faulty.update(pts + frame(index, defect).tobytes())
    assert clean.digest() == faulty.digest()


def test_contradictory_intents_are_not_hidden_by_acceptance_oracle() -> None:
    negative = CASES[0]
    positive = next(
        c
        for c in json.loads(
            (ROOT / "tests/fixtures/manifests/video_repeats.json").read_text()
        )
        if c["fixture_id"] == "video.single_duplicate.001"
    )
    observation = {
        "findings": positive["expected_findings"],
        "metrics": [],
        "states": {d: "COMPLETED" for d in positive["detectors"]},
        "errors": [],
    }
    assert not evaluate(positive, observation)
    assert evaluate(negative, observation)
    observation["findings"] = []
    assert not evaluate(negative, observation)
    assert evaluate(positive, observation)


def test_lagged_motion_measurements_and_fixed_history() -> None:
    source = np.random.default_rng(12).integers(0, 256, (32, 32, 3), dtype=np.uint8)
    history = deque([np.roll(source, i, axis=1) for i in (0, 2, 4)], maxlen=3)
    measured = temporal_features(np.roll(source, 6, axis=1), history)
    assert measured["translation_x_pixels"] == pytest.approx(2, abs=1e-5)
    assert measured["translation_y_pixels"] == pytest.approx(0, abs=1e-5)
    assert measured["translation_response"] == pytest.approx(1, abs=1e-5)
    assert all(f"lag_{i}_difference" in measured for i in (1, 2, 3))
    held = temporal_features(history[-1], history)
    assert held["lag_1_difference"] == 0
    assert held["adjacent_residual_cosine"] is None
    assert len(history) == 3


@pytest.mark.parametrize("count", [0, -1, MAX_FRAMES + 1])
def test_probe_rejects_unbounded_or_empty_requests(tmp_path: Path, count: int) -> None:
    with pytest.raises(ValueError, match="Frame count"):
        probe(tmp_path / "not_opened.mp4", tmp_path, count)
