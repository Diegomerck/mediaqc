"""Phase 5 positive fixtures, clean controls, policy boundaries and integration."""

import hashlib
import json
import logging
import threading
import time
import tracemalloc
from dataclasses import replace
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import numpy as np
import pytest
from generate_test_media.video import generate

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.app.projects import Projects
from mediaqc_engine.detectors.common import settings
from mediaqc_engine.detectors.contract import DetectorContext, DetectorResult
from mediaqc_engine.detectors.video import registry
from mediaqc_engine.detectors.video.events import repeats, sustained, transients
from mediaqc_engine.detectors.video.features import (
    Row,
    cache,
    effective_video,
    features,
    lines,
    rate,
    timestamp,
)
from mediaqc_engine.jobs.cancellation import CancellationToken, Cancelled
from mediaqc_engine.media.inspection import map_probe
from mediaqc_engine.media.tools import MediaTools
from mediaqc_engine.qc import profiles

MANIFEST = Path(__file__).resolve().parents[2] / "tests/fixtures/manifests/video.json"


def context(
    tmp_path: Path, kind: str = "clean", suffix: str = ".mp4"
) -> DetectorContext:
    source = generate("video." + kind + ".001", tmp_path / "source", suffix)
    token = CancellationToken()
    work = tmp_path / "cache" / str(uuid4())
    tools = MediaTools(cancellation=token.event, cache=work)
    metadata, streams = map_probe(tools.probe(source))
    return DetectorContext(
        str(uuid4()),
        {"absolute_path": str(source), **metadata},
        tuple({**stream, "id": str(uuid4())} for stream in streams),
        profiles.builtin(),
        str(work),
        token,
        tools,
        logging.LoggerAdapter(logging.getLogger(__name__), {}),
    )


def analyze(ctx: DetectorContext, kind: str) -> DetectorResult:
    source = Path(str(ctx.media_asset["absolute_path"]))
    before = hashlib.sha256(source.read_bytes()).digest(), source.stat().st_mtime_ns
    try:
        result = next(
            d for d in registry() if d.detector_id == "video." + kind
        ).analyze(ctx)
        json.dumps(result.findings, allow_nan=False)
        json.dumps(result.metrics, allow_nan=False)
        return result
    finally:
        assert not ctx.media_tools.pids
        assert before == (
            hashlib.sha256(source.read_bytes()).digest(),
            source.stat().st_mtime_ns,
        )


@pytest.mark.parametrize("fixture", json.loads(MANIFEST.read_text()))
def test_manifest(tmp_path: Path, fixture: dict[str, object]) -> None:
    from detector_acceptance import run_case

    result = run_case(fixture, tmp_path)
    assert result["status"] == "PASS", result["errors"]


@pytest.mark.parametrize("kind", ["clean", "static", "cut", "fade"])
def test_clean_controls_all_detectors(tmp_path: Path, kind: str) -> None:
    ctx = context(tmp_path, kind)
    for detector in registry():
        result = analyze(ctx, detector.detector_id.removeprefix("video."))
        assert not result.findings, (detector.detector_id, result.findings)


@pytest.mark.parametrize("suffix", [".mp4", ".mxf"])
def test_containers_cache_progress_and_rate(tmp_path: Path, suffix: str) -> None:
    ctx = context(tmp_path, "black", suffix)
    positions: list[float] = []
    ctx = replace(ctx, report_progress=positions.append)
    result = analyze(ctx, "black_frame")
    assert result.findings[0]["start_time_seconds"] == pytest.approx(1, abs=0.05)
    assert positions and max(positions) >= 3.9
    with patch.object(
        ctx.media_tools, "stream", side_effect=AssertionError("cache must be reused")
    ):
        assert not analyze(ctx, "decode_integrity").findings
        assert not analyze(ctx, "frame_rate").findings
        settings(ctx.qc_profile, "video.frame_rate")["expected_fps"] = 30
        assert analyze(ctx, "frame_rate").findings
    assert all(
        path.suffix in {".jsonl", ".json"} for path in Path(ctx.work_dir).iterdir()
    )


def test_4k_decode_uses_configured_bounded_measurement_size(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    source = tmp_path / "source" / "4k.mp4"
    ctx.media_tools.run(
        "ffmpeg",
        [
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(ctx.media_asset["absolute_path"]),
            "-t",
            "0.12",
            "-vf",
            "scale=3840:2160",
            "-c:v",
            "libx264rgb",
            "-crf",
            "0",
            "-preset",
            "ultrafast",
            str(source),
        ],
    )
    metadata, streams = map_probe(ctx.media_tools.probe(source))
    assert streams[0]["width"] == 3840
    ctx = replace(
        ctx,
        media_asset={**metadata, "absolute_path": str(source)},
        streams=({**streams[0], "id": "4k"},),
    )
    settings(ctx.qc_profile, "video.measurement").update(width=160, height=90)
    result = analyze(ctx, "decode_integrity")
    assert not result.findings
    measured = cast(dict[str, dict[str, object]], result.metrics["streams"])["4k"]
    assert measured["measurement_width"] == 160
    assert measured["measurement_height"] == 90
    assert measured["frame_count"] == 3


def test_pure_parsing_and_features(tmp_path: Path) -> None:
    assert rate("30000/1001") == pytest.approx(29.97002997)
    assert rate("0/0") is None and rate("N/A") is None
    assert timestamp("side_data|x=1") is None
    assert timestamp("frame|pts_time=N/A|duration_time=0.04") == {
        "pts": None,
        "duration": 0.04,
    }
    assert list(lines(iter([b"one\nt", b"wo\nthree"]))) == ["one", "two", "three"]
    with pytest.raises(AppError):
        list(lines(iter([b"x" * 65537])))
    ctx = context(tmp_path)
    black = np.zeros((16, 16, 3), dtype=np.uint8)
    measured = features(black, black, effective_video(ctx))
    assert measured["mean_luma_normalized"] == 0
    assert measured["black_pixel_ratio"] == 1
    assert measured["similarity"] == 1
    assert measured["hash_similarity"] == 1


def row(t: float, **values: float | None) -> Row:
    return {
        "time": t,
        "pts": t,
        "duration": 0.04,
        "mean_luma_normalized": 0.5,
        "similarity": 0.9,
        "hash_similarity": 0.9,
        "difference": 0.1,
        "edge_density": 0.1,
        **values,
    }


def test_duration_threshold_edges_and_static_context() -> None:
    policy = settings(profiles.builtin(), "video.black_frame")
    black = row(0, mean_luma_normalized=0.02, black_pixel_ratio=0.98)
    assert len(list(sustained(iter([black]), "black_frame", policy))) == 1
    assert not list(
        sustained(
            iter([{**black, "mean_luma_normalized": 0.0201}]), "black_frame", policy
        )
    )
    policy = settings(profiles.builtin(), "video.freeze")
    static = [
        row(i / 25, similarity=1, hash_similarity=1, difference=0) for i in range(30)
    ]
    assert not list(repeats(iter(static), "freeze", policy))
    policy["require_motion_context"] = False
    assert len(list(repeats(iter(static), "freeze", policy))) == 1


def test_static_shots_bracketed_by_cuts_are_not_freezes() -> None:
    policy = settings(profiles.builtin(), "video.freeze")
    source = [row(0, difference=0), row(0.04, difference=0.4)]
    source += [
        row(i / 25, similarity=1, hash_similarity=1, difference=0) for i in range(2, 30)
    ]
    source += [row(1.2, difference=0.4), row(1.24, difference=0)]
    assert not list(repeats(iter(source), "freeze", policy))


def test_black_duration_edges_exemptions_and_profile_severity(tmp_path: Path) -> None:
    ctx = context(tmp_path, "black")
    policy = settings(ctx.qc_profile, "video.black_frame")
    policy.update(min_duration_seconds=1.0, severity="FAIL")
    assert analyze(ctx, "black_frame").findings[0]["severity"] == "FAIL"
    policy["min_duration_seconds"] = 1.01
    assert not analyze(ctx, "black_frame").findings
    policy.update(min_duration_seconds=1.0, ignore_head_seconds=1.01)
    assert not analyze(ctx, "black_frame").findings
    policy.update(ignore_head_seconds=0, ignore_tail_seconds=2.01)
    assert not analyze(ctx, "black_frame").findings


@pytest.mark.parametrize("kind", ["duplicate_frame", "frame_cadence"])
def test_repeat_duration_count_and_similarity_boundaries(kind: str) -> None:
    policy = settings(profiles.builtin(), "video." + kind)
    source = [row(0), row(0.04, similarity=0.999), row(0.08)]
    events = list(repeats(iter(source), kind, policy))
    assert len(events) == 1 and events[0].count == 2
    assert events[0].end == pytest.approx(0.08)
    assert not list(
        repeats(iter([row(0), row(0.04, similarity=0.9989), row(0.08)]), kind, policy)
    )


def test_flash_max_duration_return_and_cut() -> None:
    policy = settings(profiles.builtin(), "video.flash")
    assert list(
        transients(
            iter([row(0), row(0.04, mean_luma_normalized=1), row(0.08)]),
            "flash",
            policy,
        )
    )
    assert not list(
        transients(
            iter(
                [row(0), *[row(i / 25, mean_luma_normalized=1) for i in range(1, 20)]]
            ),
            "flash",
            policy,
        )
    )
    assert not list(
        transients(
            iter([row(0), row(0.04, mean_luma_normalized=0.8), row(0.08)]),
            "flash",
            policy,
        )
    )


@pytest.mark.parametrize(
    "kind,patches",
    [
        ("measurement", {"width": 0}),
        ("measurement", {"height": 1921}),
        ("measurement", {"height": True}),
        ("freeze", {"similarity_threshold": 1.1}),
        ("black_frame", {"max_mean_luma_normalized": -1}),
        ("duplicate_frame", {"min_repeat_count": 1.5}),
        ("flash", {"max_duration_seconds": -1}),
        ("frame_rate", {"expected_fps": 0}),
        ("frame_rate", {"tolerance_fps": -1}),
        ("color_anomaly", {"sensitivity": float("nan")}),
        ("timestamp_integrity", {"require_pts": "yes"}),
        (
            "exposure_anomaly",
            {"shadow_luma_normalized": 0.99, "highlight_luma_normalized": 0.01},
        ),
    ],
)
def test_invalid_profiles(kind: str, patches: dict[str, object]) -> None:
    profile = profiles.builtin()
    settings(profile, "video." + kind).update(patches)
    with pytest.raises(AppError) as exc:
        profiles.validate(profile)
    assert exc.value.code == "PROFILE_INVALID"


@pytest.mark.parametrize(
    "pts,code",
    [
        (None, "MISSING_PTS"),
        (-0.01, "NEGATIVE_PTS"),
        (0.0, "DUPLICATE_PTS"),
        (-0.1, "NON_MONOTONIC_PTS"),
        (1.0, "ABNORMAL_INTERVAL"),
    ],
)
def test_original_timestamp_errors(
    tmp_path: Path, pts: float | None, code: str
) -> None:
    ctx = context(tmp_path)
    path, _ = cache(ctx, ctx.streams[0])
    path.write_text("\n".join(json.dumps(r) for r in [row(0), row(0.04, pts=pts)]))
    issue = analyze(ctx, "timestamp_integrity").findings[0]
    assert code in cast(dict[str, list[str]], issue["measurements"])["issues"]


def test_vfr_policy_and_missing_timestamp_rate(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    path, _ = cache(ctx, ctx.streams[0])
    path.write_text("\n".join(json.dumps(row(t)) for t in [0, 0.04, 0.1, 0.14]))
    assert not analyze(ctx, "timestamp_integrity").findings
    assert not analyze(ctx, "frame_rate").findings
    settings(ctx.qc_profile, "video.timestamp_integrity")[
        "allow_variable_frame_rate"
    ] = False
    assert analyze(ctx, "timestamp_integrity").findings
    settings(ctx.qc_profile, "video.timestamp_integrity")[
        "allow_variable_frame_rate"
    ] = True
    path.write_text("\n".join(json.dumps(row(t, pts=None)) for t in [0, 0.04, 0.08]))
    merged = analyze(ctx, "timestamp_integrity").findings
    assert len(merged) == 1
    assert (
        cast(dict[str, object], merged[0]["measurements"])["affected_frame_count"] == 3
    )


def test_declared_rate_and_exact_expected_rate_boundary(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    policy = settings(ctx.qc_profile, "video.frame_rate")
    policy["expected_fps"] = 25.001
    assert not analyze(ctx, "frame_rate").findings
    policy["expected_fps"] = 25.002
    assert analyze(ctx, "frame_rate").findings
    policy["expected_fps"] = None
    ctx = replace(ctx, streams=({**ctx.streams[0], "avg_frame_rate": "30/1"},))
    assert analyze(ctx, "frame_rate").findings


@pytest.mark.parametrize("shutdown", [False, True])
def test_active_video_job_cancel_and_shutdown(tmp_path: Path, shutdown: bool) -> None:
    source = generate("video.clean.001", tmp_path / "source")
    before = source.read_bytes(), source.stat().st_mtime_ns
    events: list[str] = []
    service = Projects(
        emit=lambda name, _: events.append(name), state_directory=tmp_path / "state"
    )
    try:
        project = service.dispatch(
            "project.create", {"name": "Video", "directory": str(tmp_path / "project")}
        )
        asset = service.dispatch(
            "media.inspect", {"project_id": project["id"], "absolute_path": str(source)}
        )
        started = service.dispatch(
            "analysis.start",
            {
                "project_id": project["id"],
                "media_asset_id": asset["media_asset_id"],
                "profile_key": "general_technical_qc",
                "profile_version": "1.2.0",
                "ai_mode": "OFF",
            },
        )
        deadline = time.monotonic() + 10
        while not (
            str(service.jobs.progress.get("current_detector_id")).startswith("video.")
            and service.jobs.tools is not None
            and service.jobs.tools.pids
        ):
            assert time.monotonic() < deadline
            time.sleep(0.005)
        if shutdown:
            service.jobs.shutdown()
        else:
            service.dispatch(
                "analysis.cancel", {"analysis_run_id": started["analysis_run_id"]}
            )
        assert service.jobs.worker is not None
        service.jobs.worker.join(5)
        result = service.dispatch(
            "analysis.get", {"analysis_run_id": started["analysis_run_id"]}
        )
        assert result["status"] == "CANCELLED" and result["overall_result"] is None
        assert service.jobs.tools is not None and not service.jobs.tools.pids
        assert "analysis.cancelled" in events
        assert before == (source.read_bytes(), source.stat().st_mtime_ns)
    finally:
        service.close()


def test_decode_failure_cache_and_recovered_stderr(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    with patch.object(
        ctx.media_tools,
        "stream",
        side_effect=AppError(
            "MEDIA_UNSUPPORTED", "decode error", {"stderr_excerpt": "invalid packet"}
        ),
    ):
        result = analyze(ctx, "decode_integrity")
    assert result.findings[0]["severity"] == "FAIL"
    assert "invalid packet" in json.dumps(result.findings)
    with pytest.raises(AppError):
        analyze(ctx, "freeze")


def test_real_process_cancellation_and_partial_cache(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    cancelled = threading.Event()

    def work() -> None:
        try:
            analyze(ctx, "black_frame")
        except Cancelled:
            cancelled.set()

    worker = threading.Thread(target=work)
    worker.start()
    deadline = time.monotonic() + 5
    while (
        not ctx.media_tools.pids and worker.is_alive() and time.monotonic() < deadline
    ):
        time.sleep(0.005)
    assert ctx.media_tools.pids
    ctx.cancellation.cancel()
    ctx.media_tools.cancel()
    worker.join(5)
    assert cancelled.is_set() and not worker.is_alive() and not ctx.media_tools.pids
    assert not list(Path(ctx.work_dir).glob("*-status.json"))


def test_video_persistence_reopen_disable_and_evidence_error(tmp_path: Path) -> None:
    source = generate("video.black.001", tmp_path / "source")
    before = source.read_bytes(), source.stat().st_mtime_ns
    events: list[str] = []
    service = Projects(
        emit=lambda name, _: events.append(name), state_directory=tmp_path / "state"
    )
    try:
        project = service.dispatch(
            "project.create", {"name": "Video", "directory": str(tmp_path / "project")}
        )
        asset = service.dispatch(
            "media.inspect", {"project_id": project["id"], "absolute_path": str(source)}
        )
        started = service.dispatch(
            "analysis.start",
            {
                "project_id": project["id"],
                "media_asset_id": asset["media_asset_id"],
                "profile_key": "general_technical_qc",
                "profile_version": "1.2.0",
                "ai_mode": "OFF",
            },
        )
        assert service.jobs.worker is not None
        service.jobs.worker.join(30)
        result = service.dispatch(
            "analysis.get", {"analysis_run_id": started["analysis_run_id"]}
        )
        assert result["status"] == "COMPLETED", result
        assert result["overall_result"] == "WARN"
        states = cast(list[dict[str, object]], result["detector_states"])
        assert sum(s["status"] == "COMPLETED" for s in states) == 13
        assert all(
            s["status"] == "SKIPPED"
            for s in states
            if str(s["detector_id"]).startswith("audio.")
        )
        listed = service.dispatch(
            "finding.list",
            {
                "analysis_run_id": started["analysis_run_id"],
                "detector_id": "video.black_frame",
            },
        )
        finding = cast(list[dict[str, object]], listed["findings"])[0]
        evidence = cast(list[dict[str, object]], finding["evidence"])[0]
        assert str(evidence["relative_path"]).startswith("evidence/video/")
        assert (tmp_path / "project" / str(evidence["relative_path"])).is_file()
        service.close()
        service = Projects(state_directory=tmp_path / "state")
        service.dispatch("project.open", {"project_file": project["project_file"]})
        assert (
            service.dispatch("finding.get", {"finding_id": finding["id"]})[
                "measurements"
            ]
            == finding["measurements"]
        )
        assert "analysis.completed" in events and "analysis.finding_created" in events
    finally:
        service.close()
    assert before == (source.read_bytes(), source.stat().st_mtime_ns)
    assert len(list(source.parent.iterdir())) == 1


def test_long_static_sequence_memory_is_bounded() -> None:
    policy = settings(profiles.builtin(), "video.freeze")
    policy["require_motion_context"] = False
    # More than two hours at 25 fps; producer and detector each retain O(1) rows.
    tracemalloc.start()
    try:
        events = list(
            repeats(
                (
                    row(i / 25, similarity=1, hash_similarity=1, difference=0)
                    for i in range(200_000)
                ),
                "freeze",
                policy,
            )
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(events) == 1 and events[0].count == 200_000
    assert peak < 1_000_000


def test_disabled_video_detector_and_evidence_write_failure(tmp_path: Path) -> None:
    source = generate("video.black.001", tmp_path / "source")
    service = Projects(state_directory=tmp_path / "state")
    try:
        project = service.dispatch(
            "project.create", {"name": "Video", "directory": str(tmp_path / "project")}
        )
        asset = service.dispatch(
            "media.inspect", {"project_id": project["id"], "absolute_path": str(source)}
        )
        profile = profiles.builtin()
        for detector in registry():
            settings(profile, detector.detector_id)["enabled"] = (
                detector.detector_id == "video.black_frame"
            )
        assert service.project is not None
        original = Path.write_text

        def write(
            path: Path,
            data: str,
            encoding: str | None = None,
            errors: str | None = None,
            newline: str | None = None,
        ) -> int:
            if "evidence" in path.parts:
                raise OSError("simulated evidence disk error")
            return original(
                path, data, encoding=encoding, errors=errors, newline=newline
            )

        with patch.object(Path, "write_text", write):
            started = service.jobs.start(
                service.project, str(asset["media_asset_id"]), profile
            )
            assert service.jobs.worker is not None
            service.jobs.worker.join(30)
        result = service.dispatch(
            "analysis.get", {"analysis_run_id": started["analysis_run_id"]}
        )
        assert result["status"] == "COMPLETED", result
        states = cast(list[dict[str, object]], result["detector_states"])
        video = [s for s in states if str(s["detector_id"]).startswith("video.")]
        assert len(video) == 1 and video[0]["detector_id"] == "video.black_frame"
        finding = cast(list[dict[str, object]], result["findings"])[0]
        # This fixture fails Path.write_text (metrics JSON), not FFmpeg's PNG
        # output. Phase 6 must retain those independently successful artifacts.
        references = cast(list[dict[str, object]], finding["evidence"])
        assert {item["evidence_type"] for item in references} == {
            "VIDEO_FRAME_BEFORE",
            "VIDEO_FRAME",
            "VIDEO_FRAME_AFTER",
        }
        assert all(
            (tmp_path / "project" / str(item["relative_path"])).is_file()
            for item in references
        )
        assert "EVIDENCE_WRITE_FAILED" in json.dumps(finding["metadata"])
    finally:
        service.close()
