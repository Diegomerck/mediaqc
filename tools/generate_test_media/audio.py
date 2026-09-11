"""Reproduce the original, copyright-free Phase 4 golden audio fixtures."""

import json
import wave
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parents[2]
RATE = 48000


def generate(identifier: str, destination: Path) -> Path:
    time = np.arange(RATE * 6) / RATE
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
    elif identifier != "audio.clean.001":
        raise ValueError("Unknown golden audio fixture")
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"{identifier}.wav"
    pcm: NDArray[np.int16] = (np.clip(audio, -1, 32767 / 32768) * 32768).astype("<i2")
    with wave.open(str(path), "wb") as output:
        output.setparams((audio.shape[1], 2, RATE, 0, "NONE", "not compressed"))
        output.writeframes(pcm.tobytes())
    return path


def main() -> None:
    fixtures = json.loads((ROOT / "tests/fixtures/manifests/audio.json").read_text())
    for fixture in fixtures:
        print(generate(fixture["fixture_id"], ROOT / "tests/fixtures/generated"))


if __name__ == "__main__":
    main()
