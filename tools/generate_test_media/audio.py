"""Reproduce the original, copyright-free Phase 4 golden audio fixtures."""

import json
import subprocess
import wave
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from mediaqc_engine.media.tools import tool_directory

ROOT = Path(__file__).resolve().parents[2]
RATE = 48000


def transient_samples(kind: str) -> NDArray[np.float64]:
    """Known causal constructions; sharp analytic sounds are not edit faults."""
    if kind == "masked_swapped":
        return transient_samples("masked")[:, ::-1].copy()
    if kind in {"sharp_busy", "clean_busy"}:
        left = (
            transient_samples("sharp")[:, 0]
            if kind == "sharp_busy"
            else (0.1 * np.sin(2 * np.pi * 1000 * np.arange(RATE * 6) / RATE))
        )
        right = 0.6 * np.sin(2 * np.pi * 8000 * np.arange(RATE * 6) / RATE)
        combined: NDArray[np.float64] = np.c_[left, right]
        return combined
    time = np.arange(RATE * 6) / RATE
    base = 0.1 * np.sin(2 * np.pi * 1000 * time)
    audio = base[:, None].copy()
    if kind == "dc_step_moderate":
        audio[2 * RATE :, 0] += 0.4
    elif kind == "plateau_click":
        audio[2 * RATE : 2 * RATE + 2, 0] = 0.4
    elif kind in {"click_cluster", "wide_click"}:
        if kind == "click_cluster":
            audio[2 * RATE, 0] = audio[2 * RATE + 48, 0] = 0.9
        else:
            audio[2 * RATE : 2 * RATE + 3, 0] = [0.45, 0.9, 0.45]
    elif kind in {
        "impulse_before",
        "impulse_after",
        "simultaneous",
        "delayed",
        "masked",
    }:
        offset = -1 if kind == "impulse_before" else 1 if kind == "impulse_after" else 0
        audio[2 * RATE + offset, 0] = 0.9
        if kind == "simultaneous":
            audio = np.c_[audio, audio]
        elif kind == "delayed":
            right = base.copy()
            right[2 * RATE + 48] = 0.9
            audio = np.c_[audio, right]
        elif kind == "masked":
            audio = np.c_[audio, 0.6 * np.sin(2 * np.pi * 8000 * time)]
    elif kind == "dc_step":
        audio[2 * RATE :, 0] += 0.6
    elif kind == "phase_splice":
        audio[:, 0] = 0.5 * np.sin(2 * np.pi * 250 * time)
        audio[2 * RATE + 48 :, 0] *= -1
    elif kind in {
        "sharp",
        "sharp_stereo",
        "sharp_delayed",
        "sustained",
        "sustained_shifted",
    }:
        decay = 0.08 if kind.startswith("sustained") else 0.0008

        def sound(onset: float) -> NDArray[np.float64]:
            elapsed = np.maximum(time - onset, 0)
            envelope = (1 - np.exp(-elapsed / 0.0001)) * np.exp(-elapsed / decay)
            return base + 0.8 * envelope * np.sin(2 * np.pi * 8000 * elapsed)

        audio = sound(2.015 if kind == "sustained_shifted" else 2)[:, None]
        if kind in {"sharp_stereo", "sharp_delayed"}:
            audio = np.c_[audio, sound(2.001 if kind == "sharp_delayed" else 2)]
    elif kind == "continuous_hf":
        audio[:, 0] = 0.7 * np.sin(2 * np.pi * 8000 * time)
    else:
        raise ValueError("Unknown discontinuity construction")
    return audio


def generate(identifier: str, destination: Path) -> Path:
    duration = 20 if identifier == "audio.loudness.range.001" else 6
    time = np.arange(RATE * duration) / RATE
    audio = (0.1 * np.sin(2 * np.pi * 1000 * time))[:, None]
    if identifier == "audio.clipping.001":
        audio[RATE : RATE + RATE // 10] = 1
    elif identifier == "audio.true_peak.001":
        audio[:, 0] = 1.1 * np.sin(2 * np.pi * 12000 * time + np.pi / 4)
    elif identifier == "audio.silence.001":
        audio[RATE * 2 : RATE * 4] = 0
    elif identifier == "audio.dropout.short.001":
        audio[RATE * 2 : RATE * 2 + 960] = 0
    elif identifier == "audio.discontinuity.001":
        audio[RATE * 2] = 0.9
    elif identifier.startswith("audio.discontinuity."):
        kind = identifier.split(".")[2]
        audio = transient_samples(
            {"mxf_click": "simultaneous", "mxf_sharp": "sharp_stereo"}.get(kind, kind)
        )
    elif identifier.startswith("audio.hum."):
        frequency = int(identifier.split(".")[2])
        audio[:, 0] = sum(
            0.03 / h * np.sin(2 * np.pi * frequency * h * time) for h in range(1, 6)
        )
    elif identifier == "audio.noise_floor.001":
        block = np.random.default_rng(4001).normal(0, 0.015, RATE // 10)
        audio[:, 0] = np.tile(block, 60)
    elif identifier == "audio.channel_imbalance.001":
        audio = np.c_[audio, audio * 0.1]
    elif identifier == "audio.phase_negative.001":
        audio = np.c_[audio, -audio]
    elif identifier in {
        "audio.loudness.integrated.001",
        "audio.loudness.short_term.001",
        "audio.loudness.momentary.001",
    }:
        audio *= 2
    elif identifier == "audio.loudness.range.001":
        audio[: RATE * 10] *= 0.5
        audio[RATE * 10 :] *= 2
    elif identifier == "audio.sample_peak.001":
        audio *= 9.99
    elif identifier in {
        "audio.digital_silence.001",
        "audio.unused_iso.001",
        "audio.required_silent.001",
    }:
        audio[:] = 0
    elif identifier == "audio.production_multitrack.001":
        audio = np.c_[
            audio,
            audio,
            audio * 0.1,
            audio * 0.2,
            audio * 0.3,
            audio * 0.4,
            audio * 0.5,
        ]
    elif identifier == "audio.percussive.001":
        # Smooth attack/decay, not an injected sample discontinuity.
        t = np.maximum(time - 2, 0)
        envelope = (1 - np.exp(-t / 0.003)) * np.exp(-t / 0.08)
        audio[:, 0] += 0.5 * envelope * np.sin(2 * np.pi * 3200 * t)
    elif identifier != "audio.clean.001":
        raise ValueError("Unknown golden audio fixture")
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"{identifier}.wav"
    pcm: NDArray[np.int16] = (np.clip(audio, -1, 32767 / 32768) * 32768).astype("<i2")
    with wave.open(str(path), "wb") as output:
        output.setparams((audio.shape[1], 2, RATE, 0, "NONE", "not compressed"))
        output.writeframes(pcm.tobytes())
    if identifier in {
        "audio.discontinuity.mxf_click.001",
        "audio.discontinuity.mxf_sharp.001",
    }:
        container = path.with_suffix(".mxf")
        # Two independent mono production streams plus six explicit empty ISOs.
        # The generated black picture is only an MXF container requirement.
        try:
            subprocess.run(
                [
                    str(tool_directory() / "ffmpeg.exe"),
                    "-nostdin",
                    "-v",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=black:size=720x576:rate=25",
                    "-i",
                    str(path),
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=48000:cl=mono",
                    "-filter_complex",
                    "[1:a]channelsplit=channel_layout=stereo[L][R]",
                    "-map",
                    "0:v",
                    "-map",
                    "[L]",
                    "-map",
                    "[R]",
                    *[v for _ in range(6) for v in ("-map", "2:a")],
                    "-c:v",
                    "mpeg2video",
                    "-pix_fmt",
                    "yuv422p",
                    "-c:a",
                    "pcm_s24le",
                    "-t",
                    "6",
                    str(container),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
        finally:
            path.unlink(missing_ok=True)
        return container
    return path


def main() -> None:
    fixtures = json.loads((ROOT / "tests/fixtures/manifests/audio.json").read_text())
    for fixture in fixtures:
        print(generate(fixture["fixture_id"], ROOT / "tests/fixtures/generated"))


if __name__ == "__main__":
    main()
