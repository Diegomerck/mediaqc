"""Developer-only bounded temporal measurements; no fault classification.

Reuse retained media. This never generates fixtures, changes policy, or writes to
source media. Phase correlation describes a translation model, not proven camera
motion, scene continuity, or intent (especially for zooms/repetitive textures).
"""

import argparse
import json
import math
from collections import deque
from contextlib import closing
from pathlib import Path

import cv2
import numpy as np
from detector_acceptance import artifact_path, digest

from mediaqc_engine.detectors.common import settings
from mediaqc_engine.detectors.video.features import Frame, features, timestamp
from mediaqc_engine.media.tools import MediaTools
from mediaqc_engine.qc.profiles import builtin

MAX_FRAMES = 512
WIDTH, HEIGHT = 320, 180


def temporal_features(frame: Frame, history: deque[Frame]) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    current = frame.astype(np.float32)
    for lag, previous in enumerate(reversed(history), 1):
        result[f"lag_{lag}_difference"] = float(
            np.mean(np.abs(current - previous.astype(np.float32))) / 255
        )
    if history:
        old = history[-1].astype(np.float32)
        shift, response = cv2.phaseCorrelate(old.mean(axis=2), current.mean(axis=2))
        for key, value in zip(
            ("translation_x_pixels", "translation_y_pixels", "translation_response"),
            (*shift, response),
            strict=True,
        ):
            result[key] = float(value) if math.isfinite(value) else None
        if len(history) >= 2:
            before = old - history[-2].astype(np.float32)
            after = current - old
            norm = float(np.linalg.norm(before) * np.linalg.norm(after))
            result["adjacent_residual_cosine"] = (
                float(np.sum(before * after) / norm) if norm else None
            )
    return result


def probe(source: Path, directory: Path, count: int = 192) -> dict[str, object]:
    if not 1 <= count <= MAX_FRAMES:
        raise ValueError(f"Frame count must be between 1 and {MAX_FRAMES}")
    before = digest(source), source.stat().st_size, source.stat().st_mtime_ns
    tools = MediaTools(cache=directory)
    history: deque[Frame] = deque(maxlen=3)
    rows = []
    policy = settings(builtin(), "video")
    try:
        # PTS from the source, not a nominal FPS clock. Limit selected packets;
        # decode below is capped independently. Reject any unpaired frame.
        timing = tools.run(
            "ffprobe",
            [
                "-v",
                "error",
                "-threads",
                "4",
                "-protocol_whitelist",
                "file",
                "-select_streams",
                "v:0",
                "-read_intervals",
                f"%+#{count}",
                "-show_frames",
                "-show_entries",
                "frame=pts_time,duration_time:frame_side_data=",
                "-of",
                "compact",
                "-i",
                str(source),
            ],
        )
        times = [
            row
            for line in timing.decode("utf-8").splitlines()
            if (row := timestamp(line)) is not None
        ]
        with closing(
            tools.stream(
                [
                    "-protocol_whitelist",
                    "file",
                    "-noautorotate",
                    "-i",
                    str(source),
                    "-map",
                    "0:v:0",
                    "-an",
                    "-sn",
                    "-dn",
                    "-frames:v",
                    str(count),
                    "-vf",
                    f"scale={WIDTH}:{HEIGHT}:flags=area,settb=1/1,setpts=N",
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
                block_bytes=WIDTH * HEIGHT * 3,
                reject_errors=True,
            )
        ) as chunks:
            for index, chunk in enumerate(chunks):
                if index >= count or index >= len(times):
                    raise ValueError("Decoded frame has no paired source timestamp")
                frame = np.frombuffer(chunk, dtype=np.uint8).reshape(HEIGHT, WIDTH, 3)
                row = features(frame, history[-1] if history else None, policy)
                row.update(temporal_features(frame, history))
                row.update(times[index])
                if index:
                    previous_pts, pts = times[index - 1]["pts"], row["pts"]
                    row["pts_delta"] = (
                        pts - previous_pts
                        if pts is not None and previous_pts is not None
                        else None
                    )
                rows.append(row)
                history.append(frame)
        if not rows or len(rows) != len(times):
            raise ValueError("Incomplete temporal probe")
    finally:
        tools.cancel()
        if before != (digest(source), source.stat().st_size, source.stat().st_mtime_ns):
            raise AssertionError("Source changed during temporal probe")
    return {
        "schema_version": "1.0.0",
        "source_sha256": before[0],
        "source_size": before[1],
        "source_mtime_ns": before[2],
        "frame_limit": count,
        "measurement_size": [WIDTH, HEIGHT],
        "history_frames": 3,
        "rows": rows,
        "interpretation": "Measurements only; no technical-defect or clean verdict.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--frames", type=int, default=192)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = artifact_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result = probe(args.source, output.parent, args.frames)
    output.write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
