"""Deterministic streamed developer fixtures, never an end-user media tool path."""

import json
import subprocess
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from mediaqc_engine.media.tools import tool_directory

ROOT = Path(__file__).resolve().parents[2]
FPS = 25
WIDTH, HEIGHT = 320, 180


def frame(index: int, kind: str) -> NDArray[np.uint8]:
    y, x = np.indices((HEIGHT, WIDTH))
    image = (64 + ((x + index * 11) % 128)).astype(np.uint8)
    rgb = np.repeat(image[:, :, None], 3, axis=2)
    if kind == "static":
        return frame(0, "clean")
    if kind == "cut" and index >= 50:
        rgb = 255 - rgb
    if kind == "fade":
        rgb = (rgb * (0.6 + 0.4 * abs(index - 50) / 50)).astype(np.uint8)
    if kind == "black" and 25 <= index < 50:
        rgb[:] = 0
    if kind == "near_black" and 25 <= index < 55:
        rgb[:] = 9
    if kind == "freeze" and 25 <= index < 50:
        return frame(25, "clean")
    if kind == "duplicate" and index in (26, 27):
        return frame(25, "clean")
    if kind == "flash" and 25 <= index < 28:
        rgb[:] = 255
    if kind == "luma_anomaly" and 25 <= index < 32:
        rgb[:] = 220
    if kind == "exposure" and 25 <= index < 55:
        rgb[:] = 255
    if kind == "color" and 25 <= index < 55:
        rgb[:] = [255, 0, 0]
    if kind == "visual_anomaly" and 25 <= index < 28:
        grid = (((x // 2 + y // 2) % 2) * 255).astype(np.uint8)
        rgb = np.repeat(grid[:, :, None], 3, axis=2)
    return rgb


def generate(identifier: str, directory: Path, suffix: str = ".mp4") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    kind = identifier.removeprefix("video.").removesuffix(".001")
    output = directory / (identifier + suffix)
    raw = directory / (identifier + ".rgb")
    try:
        with raw.open("wb") as target:
            for index in range(100):
                target.write(frame(index, kind).tobytes())
        filters = []
        if kind == "timestamp_irregularity":
            filters = ["-vf", "setpts=PTS+if(gte(N\\,50)\\,1/TB\\,0)"]
        if suffix == ".mxf":
            codec = [
                "-vf",
                "scale=720:576",
                "-c:v",
                "mpeg2video",
                "-pix_fmt",
                "yuv422p",
                "-g",
                "1",
                "-b:v",
                "20M",
            ]
        else:
            codec = ["-c:v", "libx264rgb", "-crf", "0", "-preset", "ultrafast"]
        subprocess.run(
            [
                str(tool_directory() / "ffmpeg.exe"),
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-f",
                "rawvideo",
                "-pixel_format",
                "rgb24",
                "-video_size",
                f"{WIDTH}x{HEIGHT}",
                "-framerate",
                str(FPS),
                "-i",
                str(raw),
                *filters,
                *codec,
                "-fps_mode",
                "passthrough",
                str(output),
            ],
            check=True,
            capture_output=True,
        )
        if kind == "decode_corrupt":
            # Damage a generated compressed packet, retaining the MP4 index so
            # inspection succeeds and the decoder must report the damaged frame.
            probe = subprocess.run(
                [
                    str(tool_directory() / "ffprobe.exe"),
                    "-v",
                    "error",
                    "-show_packets",
                    "-show_entries",
                    "packet=pos,size",
                    "-of",
                    "json",
                    str(output),
                ],
                check=True,
                capture_output=True,
            )
            packet = json.loads(probe.stdout)["packets"][25]
            with output.open("r+b") as target:
                target.seek(int(packet["pos"]))
                target.write(b"\xff" * int(packet["size"]))
    finally:
        raw.unlink(missing_ok=True)
    return output


def main() -> None:
    manifest = json.loads((ROOT / "tests/fixtures/manifests/video.json").read_text())
    for item in manifest:
        print(generate(item["fixture_id"], ROOT / "tests/fixtures/generated/video"))


if __name__ == "__main__":
    main()
