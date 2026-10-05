"""Preserve strict repeat ground truth and enforce approved bounded release limits."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from acceptance_disposition import assess
from detector_acceptance import ROOT, run_case
from generate_test_media.video import frame

CASES = json.loads(
    (ROOT / "tests/fixtures/manifests/video_repeats.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", CASES, ids=[c["fixture_id"] for c in CASES])
def test_repeat_acceptance(tmp_path: Path, case: dict[str, Any]) -> None:
    result = run_case(case, tmp_path)
    # A lossy copy is a real repeated source image, even when its decoded RGB
    # values differ. An exact-equality-only fix must fail this positive gate.
    if case["fixture_id"] == "video.single_duplicate_lossy.001":
        with (tmp_path / "cache/video-0.jsonl").open(encoding="utf-8") as source:
            pair = next(json.loads(line) for i, line in enumerate(source) if i == 26)
        assert 0 < pair["difference"] < 0.001
    result["release"] = assess(case, result["observation"])
    (tmp_path / "acceptance.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    assert not result["release"]["blocking"], result


@pytest.mark.parametrize("kind", ["zoom_settle", "low_motion"])
def test_negative_motion_really_changes_pixels(kind: str) -> None:
    assert not np.array_equal(frame(25, kind), frame(26, kind))


@pytest.mark.parametrize("kind", ["single_duplicate", "single_duplicate_lossy"])
def test_positive_copy_has_identical_source_images(kind: str) -> None:
    assert np.array_equal(frame(25, kind), frame(26, kind))
    assert not np.array_equal(frame(26, kind), frame(27, kind))


def test_cadence_injection_has_four_isolated_copies() -> None:
    repeats = [
        i
        for i in range(1, 100)
        if np.array_equal(frame(i - 1, "broken_cadence"), frame(i, "broken_cadence"))
    ]
    assert repeats == [20, 40, 60, 80]
