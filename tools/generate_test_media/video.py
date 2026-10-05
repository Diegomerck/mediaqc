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
    if kind in {"intentional_hold", "intentional_hold_lossy"}:
        # An authored animation clock intentionally pauses for one output frame
        # then catches up. No acquisition/transmission failure occurred. Its
        # raster output is observationally identical to single_duplicate.
        held_position = index if index != 26 else 25
        return frame(held_position, "clean")
    if kind == "intentional_periodic_hold":
        # Deliberate rhythmic held imagery, with the same output schedule as the
        # broken-cadence injection. Output PTS alone cannot express this intent.
        held_position = index - 1 if index in (20, 40, 60, 80) else index
        return frame(held_position, "clean")
    if kind == "broken_cadence_lossy":
        return frame(index, "broken_cadence")
    if kind == "duplicate_at_cut":
        # A real repeat immediately before a cut must not disappear under a
        # blanket cut-adjacency veto. It replaces frame 25 with frame 24.
        image = frame(24 if index == 25 else index, "clean")
        return 255 - image if index >= 26 else image
    if kind == "low_motion":
        # Independently rendered subpixel translation, including quantization.
        texture = 128 + 45 * np.sin((x + index * 0.002) * 0.3)
        texture += 45 * np.sin(y * 0.4)
        return np.repeat(texture.astype(np.uint8)[:, :, None], 3, axis=2)
    if kind in {"single_duplicate", "single_duplicate_lossy"}:
        return frame(25 if index == 26 else index, "clean")
    if kind == "duplicate_lossy":
        return frame(index, "duplicate")
    if kind in {"repeat_six", "repeat_seven"}:
        end = 31 if kind == "repeat_six" else 32
        return frame(25 if 25 <= index < end else index, "clean")
    if kind == "repeat_tail":
        return frame(97 if index >= 97 else index, "clean")
    if kind == "broken_cadence":
        # Preserve CFR timestamps but replace every twentieth moving image with
        # its predecessor. This is injected content stutter, not a VFR policy test.
        return frame(index - 1 if index in (20, 40, 60, 80) else index, "clean")
    if kind == "static_between_cuts":
        # A legitimate two-frame static insert bounded by ordinary hard cuts.
        return frame(0, "clean") if index in (25, 26) else frame(index, "clean")
    if kind == "zoom_settle_lossy":
        return frame(index, "zoom_settle")
    if kind in {"zoom", "zoom_settle"}:
        position = 25.001 if kind == "zoom_settle" and index == 26 else index
        scale = 1 + position * 0.02
        texture = 128 + 45 * np.sin((x - WIDTH / 2) / scale * 0.3)
        texture += 45 * np.sin((y - HEIGHT / 2) / scale * 0.4)
        return np.repeat(texture.astype(np.uint8)[:, :, None], 3, axis=2)
    image = (64 + ((x + index * 11) % 128)).astype(np.uint8)
    rgb = np.repeat(image[:, :, None], 3, axis=2)
    if kind == "static":
        return frame(0, "clean")
    if kind == "cut" and index >= 50:
        rgb = 255 - rgb
    if kind == "fade":
        rgb = (rgb * (0.6 + 0.4 * abs(index - 50) / 50)).astype(np.uint8)
    if kind == "auto_exposure":
        # Permanent exposure adaptation, not a flash followed by a return.
        gain = 0.65 + 0.3 * np.clip((index - 35) / 10, 0, 1)
        rgb = (rgb * gain).astype(np.uint8)
    if kind == "focus_adaptation":
        import cv2

        if 25 <= index < 55:
            rgb = cv2.GaussianBlur(rgb, (9, 9), 2).astype(np.uint8)
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
    kind = identifier.removeprefix("video.").removesuffix(".001")
    if kind not in {
        "clean",
        "static",
        "cut",
        "fade",
        "black",
        "near_black",
        "freeze",
        "duplicate",
        "flash",
        "luma_anomaly",
        "exposure",
        "color",
        "visual_anomaly",
        "timestamp_irregularity",
        "decode_corrupt",
        "zoom",
        "zoom_settle",
        "auto_exposure",
        "focus_adaptation",
        "rate_mismatch",
        "low_motion",
        "single_duplicate",
        "single_duplicate_lossy",
        "duplicate_lossy",
        "broken_cadence",
        "static_between_cuts",
        "zoom_settle_lossy",
        "repeat_six",
        "repeat_seven",
        "repeat_tail",
        "intentional_hold",
        "intentional_hold_lossy",
        "intentional_periodic_hold",
        "broken_cadence_lossy",
        "duplicate_at_cut",
    }:
        raise ValueError("Unknown golden video fixture")
    directory.mkdir(parents=True, exist_ok=True)
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
        elif kind.endswith("_lossy"):
            codec = ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p"]
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
