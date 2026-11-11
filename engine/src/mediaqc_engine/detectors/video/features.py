"""Bounded per-frame OpenCV features and disk-backed decoded timestamp cache.

FFprobe supplies original decoded PTS; FFmpeg emits one RGB frame per decoded
frame with passthrough sync and transport-only ordinal timestamps. No OpenCV
container reader or alternate child owner.
"""

import json
from collections.abc import Iterator
from contextlib import closing, nullcontext
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.detectors.common import number, settings
from mediaqc_engine.detectors.contract import DetectorContext
from mediaqc_engine.media.inspection import number as optional_number

Frame = NDArray[np.uint8]
Row = dict[str, float | None]
LUMA_WEIGHTS: NDArray[np.float32] = np.array(
    [0.2126, 0.7152, 0.0722], dtype=np.float32
)


@dataclass
class FrameFeatures:
    rgb: NDArray[np.float32]
    luma: NDArray[np.float32]
    grey: Frame
    hist: NDArray[np.float64]
    edge: float
    small: Frame


def edge_density(grey: Frame) -> float:
    # First derivatives retain dense corruption edges that Canny suppression
    # removes. 64 is an image-feature extraction constant, not a QC policy gate.
    dx = cv2.Sobel(grey, cv2.CV_32F, 1, 0)
    dy = cv2.Sobel(grey, cv2.CV_32F, 0, 1)
    return float(np.mean(np.maximum(np.abs(dx), np.abs(dy)) > 64))


def rate(value: object) -> float | None:
    try:
        result = float(Fraction(str(value)))
        return result if result > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def lines(chunks: Iterator[bytes]) -> Iterator[str]:
    pending = b""
    for chunk in chunks:
        pending += chunk
        while b"\n" in pending:
            line, pending = pending.split(b"\n", 1)
            yield line.decode("utf-8", errors="replace")
        if len(pending) > 65536:
            raise AppError("MEDIA_UNSUPPORTED", "Video metadata line is too large")
    if pending:
        yield pending.decode("utf-8", errors="replace")


def timestamp(line: str) -> Row | None:
    if not line.startswith("frame|"):
        return None
    fields = dict(part.split("=", 1) for part in line.split("|")[1:] if "=" in part)
    return {
        "pts": optional_number(fields.get("pts_time")),
        "duration": optional_number(
            fields.get("duration_time", fields.get("pkt_duration_time"))
        ),
    }


def extract_frame_features(frame: Frame) -> FrameFeatures:
    rgb: NDArray[np.float32] = (frame.astype(np.float32) / 255).astype(np.float32)
    luma: NDArray[np.float32] = rgb @ LUMA_WEIGHTS
    grey = np.round(luma * 255).astype(np.uint8)
    hist = np.histogram(luma, bins=32, range=(0, 1))[0] / luma.size
    edge = edge_density(grey)
    small = cast(Frame, cv2.resize(grey, (9, 8), interpolation=cv2.INTER_AREA))
    return FrameFeatures(
        rgb=rgb,
        luma=luma,
        grey=grey,
        hist=hist,
        edge=edge,
        small=small,
    )


def compute_features(
    frame: Frame,
    previous: FrameFeatures | None,
    policy: dict[str, object],
) -> tuple[Row, FrameFeatures]:
    current = extract_frame_features(frame)
    difference, hash_similarity, divergence, edge_delta = 0.0, 1.0, 0.0, 0.0
    if previous is not None:
        difference = float(np.mean(np.abs(current.rgb - previous.rgb)))
        hash_similarity = float(
            np.mean(
                (current.small[:, 1:] > current.small[:, :-1])
                == (previous.small[:, 1:] > previous.small[:, :-1])
            )
        )
        divergence = float(np.sum(np.abs(current.hist - previous.hist)) / 2)
        edge_delta = abs(current.edge - previous.edge)
    black = cast(dict[str, object], policy["black_frame"])
    near = cast(dict[str, object], policy["near_black_frame"])
    exposure = cast(dict[str, object], policy["exposure_anomaly"])
    color = cast(dict[str, object], policy["color_anomaly"])
    row: Row = {
        "mean_luma_normalized": float(np.mean(current.luma)),
        "black_pixel_ratio": float(
            np.mean(current.luma <= number(black, "pixel_luma_threshold_normalized"))
        ),
        "near_black_pixel_ratio": float(
            np.mean(current.luma <= number(near, "pixel_luma_threshold_normalized"))
        ),
        "shadow_ratio": float(
            np.mean(current.luma <= number(exposure, "shadow_luma_normalized"))
        ),
        "highlight_ratio": float(
            np.mean(current.luma >= number(exposure, "highlight_luma_normalized"))
        ),
        "dominant_pixel_ratio": float(
            np.mean(
                np.ptp(current.rgb, axis=2)
                >= number(color, "min_channel_spread_normalized")
            )
        ),
        "channel_spread_normalized": float(np.ptp(np.mean(current.rgb, axis=(0, 1)))),
        "difference": difference,
        "similarity": 1 - difference,
        "hash_similarity": hash_similarity,
        "histogram_divergence": divergence,
        "edge_density": current.edge,
        "edge_density_delta": edge_delta,
    }
    return row, current


def features(
    frame: Frame,
    previous: Frame | None,
    policy: dict[str, object],
    prev_features: FrameFeatures | None = None,
) -> Row:
    # Full-range RGB from FFmpeg; BT.709 normalized luma, independent of bit depth.
    if prev_features is None and previous is not None:
        prev_features = extract_frame_features(previous)
    row, _ = compute_features(frame, prev_features, policy)
    return row


def effective_video(context: DetectorContext) -> dict[str, object]:
    from mediaqc_engine.qc.profiles import builtin

    defaults = settings(builtin(), "video")
    supplied = settings(context.qc_profile, "video")
    return {
        key: {
            **cast(dict[str, object], value),
            **cast(dict[str, object], supplied.get(key, {})),
        }
        for key, value in defaults.items()
    }


def cache(
    context: DetectorContext, stream: dict[str, object]
) -> tuple[Path, dict[str, object]]:
    directory = Path(context.work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    name = f"video-{stream['stream_index']}"
    path, status = directory / f"{name}.jsonl", directory / f"{name}-status.json"
    if status.exists():
        return path, json.loads(status.read_text())
    policy = effective_video(context)
    ts_policy = cast(dict[str, object], policy.get("timestamp_integrity", {}))
    need_packet_timestamps = bool(ts_policy.get("enabled", True))
    size = cast(dict[str, object], policy["measurement"])
    width, height = int(str(size["width"])), int(str(size["height"]))
    source = str(context.media_asset["absolute_path"])
    index = str(stream["stream_index"])
    timestamps = directory / f"{name}-pts.jsonl"
    errors: list[dict[str, object]] = []
    count = 0
    if need_packet_timestamps:
        with timestamps.open("w", encoding="utf-8") as output:
            try:
                with closing(
                    context.media_tools.stream(
                        [
                            "-threads",
                            "4",
                            "-protocol_whitelist",
                            "file",
                            "-select_streams",
                            index,
                            "-show_frames",
                            "-show_entries",
                            "frame=pts_time,duration_time,pkt_duration_time",
                            "-of",
                            "compact",
                            "-i",
                            source,
                        ],
                        tool="ffprobe",
                        reject_errors=True,
                    )
                ) as chunks:
                    for line in lines(chunks):
                        context.cancellation.check()
                        row = timestamp(line)
                        if row is not None:
                            output.write(json.dumps(row) + "\n")
                            count += 1
                            if count % 100 == 0:
                                context.report_progress(max(0, row["pts"] or 0))
            except AppError as exc:
                errors.append({"stage": "timestamps", "code": exc.code, **exc.details})
    prev_features: FrameFeatures | None = None
    decoded = 0
    first_time: float | None = None
    step = 1 / (
        rate(stream.get("avg_frame_rate")) or rate(stream.get("real_frame_rate")) or 25
    )
    position = float(str(stream.get("start_time_seconds") or 0))
    pts_context = (
        timestamps.open(encoding="utf-8")
        if need_packet_timestamps and timestamps.exists()
        else nullcontext()
    )
    with (
        pts_context as pts,
        path.open("w", encoding="utf-8") as output,
    ):
        try:
            with closing(
                context.media_tools.stream(
                    [
                        "-protocol_whitelist",
                        "file",
                        "-noautorotate",
                        "-i",
                        source,
                        "-map",
                        f"0:{index}",
                        "-an",
                        "-sn",
                        "-dn",
                        "-vf",
                        # Raw RGB carries no timing. Give its encoder/muxer an
                        # ordinal clock so source PTS cannot collide when rounded
                        # to the default output timebase. Measurements above/below
                        # still use unmodified ffprobe PTS, paired by frame order.
                        f"scale={width}:{height}:flags=area,settb=1/1,setpts=N",
                        "-enc_time_base",
                        "filter",
                        "-fps_mode",
                        "passthrough",
                        "-pix_fmt",
                        "rgb24",
                        "-f",
                        "rawvideo",
                        "pipe:1",
                    ],
                    block_bytes=width * height * 3,
                    reject_errors=True,
                )
            ) as chunks:
                for chunk in chunks:
                    context.cancellation.check()
                    if len(chunk) != width * height * 3:
                        raise AppError("MEDIA_UNSUPPORTED", "Truncated raw video frame")
                    frame = np.frombuffer(chunk, dtype=np.uint8).reshape(
                        height, width, 3
                    )
                    line = pts.readline() if pts is not None else ""
                    timing: Row = (
                        json.loads(line)
                        if line
                        else {"pts": position, "duration": step}
                    )
                    row, prev_features = compute_features(frame, prev_features, policy)
                    actual = timing["pts"]
                    duration = timing["duration"] or step
                    row.update(timing)
                    row["pts"] = actual if actual is not None else position
                    row["time"] = row["pts"]
                    if first_time is None:
                        first_time = row["time"]
                    row["duration"] = max(0, duration)
                    output.write(json.dumps(row, allow_nan=False) + "\n")
                    position = value(row, "time") + duration
                    decoded += 1
                    if decoded % 25 == 0:
                        context.report_progress(max(0, position))
        except AppError as exc:
            errors.append(
                {
                    "stage": "frames",
                    "code": exc.code,
                    "message": exc.message,
                    **exc.details,
                }
            )
    context.cancellation.check()
    if (need_packet_timestamps and decoded != count) or not decoded:
        errors.append(
            {
                "code": "FRAME_COUNT_MISMATCH",
                "timestamp_frames": count,
                "decoded_frames": decoded,
            }
        )
    declared = optional_number(stream.get("duration_seconds"))
    measured_duration = position - first_time if first_time is not None else 0
    decode_policy = cast(dict[str, object], policy["decode_integrity"])
    if declared is not None and declared - measured_duration > number(
        decode_policy, "max_missing_duration_seconds"
    ):
        errors.append(
            {
                "code": "INCOMPLETE_DURATION",
                "declared_duration_seconds": declared,
                "decoded_duration_seconds": measured_duration,
            }
        )
    summary: dict[str, object] = {
        "frame_count": decoded,
        "errors": errors,
        "measurement_width": width,
        "measurement_height": height,
        "measurement_space": (
            "FFmpeg full-range RGB24 / BT.709 luma; no HDR tone mapping"
        ),
    }
    status.write_text(json.dumps(summary), encoding="utf-8")
    return path, summary


def rows(path: Path, context: DetectorContext) -> Iterator[Row]:
    with path.open(encoding="utf-8") as source:
        for index, line in enumerate(source):
            context.cancellation.check()
            row: Row = json.loads(line)
            if index % 100 == 0:
                context.report_progress(max(0, row["time"] or 0))
            yield row


def value(row: Row, key: str) -> float:
    return row[key] or 0.0
