"""Unit tests for EventDetector head/tail filtering and full-duration span handling."""

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from mediaqc_engine.detectors.contract import DetectorContext
from mediaqc_engine.detectors.video import registry
from mediaqc_engine.detectors.video.events import EventDetector
from mediaqc_engine.jobs.cancellation import CancellationToken
from mediaqc_engine.qc import profiles


def make_context(
    tmp_path: Path,
    profile_mods: dict[str, object],
    duration: float = 10.0,
) -> tuple[DetectorContext, dict[str, object]]:
    profile = profiles.builtin()
    video_profile = profile.setdefault("video", {})
    assert isinstance(video_profile, dict)
    for k, v in profile_mods.items():
        if (
            isinstance(v, dict)
            and k in video_profile
            and isinstance(video_profile[k], dict)
        ):
            video_profile[k].update(v)
        else:
            video_profile[k] = v

    stream: dict[str, object] = {
        "id": "v0",
        "media_type": "video",
        "stream_index": 0,
        "duration_seconds": duration,
        "start_time_seconds": 0.0,
    }
    ctx = DetectorContext(
        analysis_run_id="run-test",
        media_asset={"absolute_path": "dummy.mp4", "duration_seconds": duration},
        streams=(stream,),
        qc_profile=profile,
        work_dir=str(tmp_path),
        cancellation=CancellationToken(),
        media_tools=MagicMock(),
        logger=logging.LoggerAdapter(logging.getLogger("test"), {}),
    )
    return ctx, stream


def write_rows(path: Path, rows: Sequence[dict[str, float]]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_sustained_blackout_spanning_full_duration_not_discarded_by_head_padding(
    tmp_path: Path,
) -> None:
    ctx, stream = make_context(
        tmp_path,
        {
            "black_frame": {
                "enabled": True,
                "min_duration_seconds": 0.5,
                "ignore_head_seconds": 2.0,
                "ignore_tail_seconds": 2.0,
            }
        },
        duration=10.0,
    )
    cache_path = tmp_path / "cache.jsonl"
    fps = 25
    total_frames = int(10.0 * fps)
    rows: list[dict[str, float]] = [
        {
            "time": i / fps,
            "duration": 1.0 / fps,
            "pts": i / fps,
            "mean_luma_normalized": 0.0,
            "black_pixel_ratio": 1.0,
            "difference": 0.0,
            "similarity": 1.0,
            "hash_similarity": 1.0,
            "edge_density": 0.0,
            "edge_density_delta": 0.0,
            "histogram_divergence": 0.0,
            "shadow_ratio": 1.0,
            "highlight_ratio": 0.0,
            "dominant_pixel_ratio": 1.0,
            "channel_spread_normalized": 0.0,
        }
        for i in range(total_frames)
    ]
    write_rows(cache_path, rows)

    detector = cast(
        EventDetector,
        next(d for d in registry() if d.detector_id == "video.black_frame"),
    )
    cache_mock: tuple[Path, dict[str, object]] = (cache_path, {"errors": []})
    with patch("mediaqc_engine.detectors.video.events.cache", return_value=cache_mock):
        result = detector.measure(ctx, stream)

    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding["title"] == "Total video signal loss"
    assert finding["start_time_seconds"] == pytest.approx(0.0)
    assert finding["end_time_seconds"] == pytest.approx(10.0)


def test_partial_blackout_within_head_padding_is_discarded(tmp_path: Path) -> None:
    ctx, stream = make_context(
        tmp_path,
        {
            "black_frame": {
                "enabled": True,
                "min_duration_seconds": 0.5,
                "ignore_head_seconds": 2.0,
            }
        },
        duration=10.0,
    )
    cache_path = tmp_path / "cache.jsonl"
    fps = 25
    rows: list[dict[str, float]] = []
    for i in range(int(10.0 * fps)):
        is_black = i < int(1.0 * fps)
        rows.append(
            {
                "time": i / fps,
                "duration": 1.0 / fps,
                "pts": i / fps,
                "mean_luma_normalized": 0.0 if is_black else 0.5,
                "black_pixel_ratio": 1.0 if is_black else 0.0,
                "difference": 0.0,
                "similarity": 1.0,
                "hash_similarity": 1.0,
                "edge_density": 0.0,
                "edge_density_delta": 0.0,
                "histogram_divergence": 0.0,
                "shadow_ratio": 1.0 if is_black else 0.0,
                "highlight_ratio": 0.0,
                "dominant_pixel_ratio": 1.0 if is_black else 0.0,
                "channel_spread_normalized": 0.0,
            }
        )
    write_rows(cache_path, rows)

    detector = cast(
        EventDetector,
        next(d for d in registry() if d.detector_id == "video.black_frame"),
    )
    cache_mock: tuple[Path, dict[str, object]] = (cache_path, {"errors": []})
    with patch("mediaqc_engine.detectors.video.events.cache", return_value=cache_mock):
        result = detector.measure(ctx, stream)

    # 1.0s < 10.0 * 0.8 and start < 2.0s head, so discarded as head padding
    assert len(result.findings) == 0


def test_sustained_freeze_spanning_full_duration_not_discarded_by_head_padding(
    tmp_path: Path,
) -> None:
    ctx, stream = make_context(
        tmp_path,
        {
            "freeze": {
                "enabled": True,
                "min_duration_seconds": 0.5,
                "ignore_head_seconds": 2.0,
                "ignore_tail_seconds": 2.0,
                "require_motion_context": False,
            }
        },
        duration=10.0,
    )
    cache_path = tmp_path / "cache.jsonl"
    fps = 25
    total_frames = int(10.0 * fps)
    rows: list[dict[str, float]] = [
        {
            "time": i / fps,
            "duration": 1.0 / fps,
            "pts": i / fps,
            "mean_luma_normalized": 0.5,
            "black_pixel_ratio": 0.0,
            "difference": 0.0,
            "similarity": 1.0,
            "hash_similarity": 1.0,
            "edge_density": 0.2,
            "edge_density_delta": 0.0,
            "histogram_divergence": 0.0,
            "shadow_ratio": 0.0,
            "highlight_ratio": 0.0,
            "dominant_pixel_ratio": 0.0,
            "channel_spread_normalized": 0.1,
        }
        for i in range(total_frames)
    ]
    write_rows(cache_path, rows)

    detector = cast(
        EventDetector,
        next(d for d in registry() if d.detector_id == "video.freeze"),
    )
    cache_mock: tuple[Path, dict[str, object]] = (cache_path, {"errors": []})
    with patch("mediaqc_engine.detectors.video.events.cache", return_value=cache_mock):
        result = detector.measure(ctx, stream)

    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding["title"] == "Video freeze candidate"
    assert finding["start_time_seconds"] == pytest.approx(0.0)
    assert finding["end_time_seconds"] == pytest.approx(10.0)
