"""Raw RGB transport timing must not masquerade as source decode corruption."""

import hashlib
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.app.projects import Projects
from mediaqc_engine.detectors.common import settings
from mediaqc_engine.detectors.contract import DetectorContext
from mediaqc_engine.detectors.video import registry
from mediaqc_engine.detectors.video.features import cache, rows
from mediaqc_engine.jobs.cancellation import CancellationToken
from mediaqc_engine.media.inspection import map_probe
from mediaqc_engine.media.tools import MediaTools
from mediaqc_engine.qc import profiles


def test_rawvideo_mux_dts_is_not_source_decode_failure(tmp_path: Path) -> None:
    tools = MediaTools(cache=tmp_path / "tools")
    source = tmp_path / "clustered-pts.mp4"
    # Valid strictly increasing MP4 PTS, clustered more closely than the
    # default rawvideo encoder timebase. All 25 frames remain decodable.
    tools.run(
        "ffmpeg",
        [
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=32x32:rate=25:duration=1",
            "-vf",
            r"settb=1/1000,setpts=floor(N/2)*80+mod(N\,2)",
            "-enc_time_base",
            "filter",
            "-fps_mode",
            "passthrough",
            "-c:v",
            "libx264rgb",
            "-preset",
            "ultrafast",
            str(source),
        ],
    )
    before = hashlib.sha256(source.read_bytes()).digest(), source.stat().st_mtime_ns
    old_arguments = [
        "-i",
        str(source),
        "-vf",
        "scale=32:32:flags=area",
        "-fps_mode",
        "passthrough",
        "-pix_fmt",
        "rgb24",
        "-f",
        "rawvideo",
        "pipe:1",
    ]
    old = subprocess.run(
        [
            str(tools.directory / "ffmpeg.exe"),
            "-nostdin",
            "-v",
            "error",
            *old_arguments,
        ],
        capture_output=True,
        check=True,
    )
    assert old.returncode == 0 and len(old.stdout) == 25 * 32 * 32 * 3
    assert b"non monotonically increasing dts to muxer" in old.stderr
    chunks: list[bytes] = []
    with pytest.raises(AppError) as failure:
        chunks.extend(
            tools.stream(old_arguments, block_bytes=32 * 32 * 3, reject_errors=True)
        )
    assert len(chunks) == 25
    assert failure.value.code == "MEDIA_UNSUPPORTED"
    assert failure.value.details["exit_code"] == 0
    assert "non monotonically increasing dts" in str(
        failure.value.details["stderr_excerpt"]
    )

    metadata, streams = map_probe(tools.probe(source))
    timing_arguments = [
        "-select_streams",
        "0",
        "-show_frames",
        "-show_entries",
        "frame=pts_time,duration_time,pkt_duration_time",
        "-of",
        "compact",
        "-i",
        str(source),
    ]
    serial = b"".join(
        tools.stream(
            ["-threads", "1", *timing_arguments], tool="ffprobe", reject_errors=True
        )
    )
    threaded = b"".join(
        tools.stream(
            ["-threads", "4", *timing_arguments], tool="ffprobe", reject_errors=True
        )
    )
    assert threaded == serial
    ctx = DetectorContext(
        str(uuid4()),
        {"absolute_path": str(source), **metadata},
        tuple({**stream, "id": str(uuid4())} for stream in streams),
        profiles.builtin(),
        str(tmp_path / "measurements"),
        CancellationToken(),
        tools,
        logging.LoggerAdapter(logging.getLogger(__name__), {}),
    )
    settings(ctx.qc_profile, "video.measurement").update(width=32, height=32)
    path, summary = cache(ctx, ctx.streams[0])
    assert summary["errors"] == []
    assert summary["frame_count"] == 25
    timing = [row["pts"] for row in rows(path, ctx)]
    assert timing[:4] == pytest.approx([0, 0.001, 0.08, 0.081])
    for detector in registry():
        result = detector.analyze(ctx)  # No downstream FAILED executions.
        if detector.detector_id in {
            "video.decode_integrity",
            "video.timestamp_integrity",
        }:
            assert not result.findings
    # Original source timing still drives policy; no synthetic output times leak.
    settings(ctx.qc_profile, "video.timestamp_integrity")[
        "allow_variable_frame_rate"
    ] = False
    timestamp_detector = next(
        d for d in registry() if d.detector_id == "video.timestamp_integrity"
    )
    assert timestamp_detector.analyze(ctx).findings
    # Duplicate source PTS also remain visible to the timestamp detector only.
    values = [json.loads(line) for line in path.read_text().splitlines()]
    values[1]["pts"] = values[0]["pts"]
    path.write_text("".join(json.dumps(row) + "\n" for row in values))
    assert "DUPLICATE_PTS" in json.dumps(timestamp_detector.analyze(ctx).findings)
    assert not registry()[0].analyze(ctx).findings

    # Exercise persisted one-file batch classification through the real engine.
    service = Projects(state_directory=tmp_path / "state")
    try:
        project = service.dispatch(
            "project.create", {"name": "DTS", "directory": str(tmp_path / "project")}
        )
        batch = service.dispatch(
            "batch.create",
            {
                "project_id": project["id"],
                "name": "DTS",
                "source_kind": "FILE",
                "absolute_path": str(source),
            },
        )

        def wait(status: str) -> dict[str, object]:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                snapshot = service.dispatch(
                    "batch.get", {"batch_id": batch["batch_id"]}
                )
                if snapshot["status"] == status:
                    return snapshot
                assert snapshot["status"] not in {"FAILED", "STOPPED"}, snapshot
                time.sleep(0.02)
            raise AssertionError(f"batch did not reach {status}")

        wait("READY")
        service.dispatch(
            "batch.start",
            {
                "batch_id": batch["batch_id"],
                "profile_key": "general_technical_qc",
                "profile_version": "1.2.0",
                "ai_mode": "OFF",
            },
        )
        finished = wait("COMPLETED")
        assert cast(dict[str, int], finished["counts"])["error"] == 0
        page = service.dispatch("batch.items", {"batch_id": batch["batch_id"]})
        item = cast(list[dict[str, object]], page["items"])[0]
        assert item["status"] == "COMPLETED"
        run = service.dispatch(
            "analysis.get", {"analysis_run_id": item["analysis_run_id"]}
        )
        states = cast(list[dict[str, object]], run["detector_states"])
        video = [
            state for state in states if str(state["detector_id"]).startswith("video.")
        ]
        assert len(video) == len(registry())
        assert all(state["status"] == "COMPLETED" for state in video)
    finally:
        service.close()
    assert before == (
        hashlib.sha256(source.read_bytes()).digest(),
        source.stat().st_mtime_ns,
    )
    assert not tools.pids
