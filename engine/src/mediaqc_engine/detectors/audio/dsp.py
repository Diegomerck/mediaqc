"""Bounded PCM windows and pure numerical primitives. No QC policy here."""

from collections.abc import Generator, Iterator
from contextlib import closing
from typing import cast

import numpy as np
from numpy.typing import NDArray

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.detectors.audio.pcm import chunks
from mediaqc_engine.detectors.contract import DetectorContext

type Samples = NDArray[np.float64]


def db(amplitude: float) -> float:
    # Numerical display floor, not a policy threshold. JSON cannot encode -Infinity.
    return float(20 * np.log10(max(amplitude, 1e-15)))


def rms(samples: Samples) -> float:
    return float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0


def correlation(samples: Samples, left: int, right: int) -> float | None:
    a, b = samples[:, left], samples[:, right]
    a, b = a - a.mean(), b - b.mean()
    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.clip(np.dot(a, b) / norm, -1, 1)) if norm > 1e-20 else None


def windows(
    context: DetectorContext,
    stream: dict[str, object],
    seconds: float,
    overlap: float = 0,
) -> Generator[tuple[float, Samples, int], None, None]:
    rate, channels = (
        int(str(stream["sample_rate_hz"])),
        int(str(stream["channel_count"])),
    )
    if rate <= 0 or channels <= 0 or channels > 64:
        raise AppError("MEDIA_UNSUPPORTED", "Unsupported audio rate or channel count")
    count = max(1, round(rate * seconds))
    hop = max(1, round(count * (1 - overlap)))
    pending = np.empty((0, channels), dtype=np.float64)
    position = 0
    reported = -1
    decoded_samples = 0
    arguments = [
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        str(context.media_asset["absolute_path"]),
        "-map",
        f"0:{stream['stream_index']}",
        "-vn",
        "-sn",
        "-dn",
        "-c:a",
        "pcm_f64le",
        "-f",
        "f64le",
        "pipe:1",
    ]
    with closing(
        chunks(
            context,
            stream,
            arguments,
            max(count, 65536 // (channels * 8)) * channels * 8,
        )
    ) as decoded:
        for chunk in decoded:
            context.cancellation.check()
            if len(chunk) % (8 * channels):
                raise AppError("MEDIA_UNSUPPORTED", "Incomplete decoded audio sample")
            block = np.frombuffer(chunk, dtype="<f8").reshape(-1, channels)
            decoded_samples += len(block)
            if not np.isfinite(block).all():
                raise AppError("MEDIA_UNSUPPORTED", "Non-finite decoded audio")
            pending = np.concatenate((pending, block))
            while len(pending) >= count:
                context.cancellation.check()
                if int(position / rate) != reported:
                    reported = int(position / rate)
                    context.report_progress(position / rate)
                yield position / rate, pending[:count], rate
                position += hop
                pending = pending[hop:]
        if len(pending) and (overlap == 0 or position == 0):
            yield position / rate, pending, rate
        if decoded_samples == 0:
            raise AppError(
                "MEDIA_UNSUPPORTED", "Audio stream contains no decoded samples"
            )


def power_windows(
    context: DetectorContext, stream: dict[str, object], seconds: float
) -> Iterator[tuple[float, float, Samples]]:
    """Vectorize window power without changing sample boundaries or reduction order."""
    rate = int(str(stream["sample_rate_hz"]))
    count = max(1, round(rate * seconds))
    position = 0
    for _, samples, _ in windows(context, stream, count * 256 / rate):
        whole = len(samples) // count * count
        powers = np.mean(
            np.square(samples[:whole]).reshape(-1, count, samples.shape[1]), axis=1
        )
        for power in powers:
            context.cancellation.check()
            yield position / rate, position / rate + count / rate, power
            position += count
        if whole < len(samples):
            yield (
                position / rate,
                position / rate + (len(samples) - whole) / rate,
                np.mean(samples[whole:] ** 2, axis=0),
            )
            position += len(samples) - whole


def spectrum(samples: Samples, rate: int) -> tuple[Samples, Samples, float]:
    window = np.hanning(len(samples))
    power = np.mean(np.abs(np.fft.rfft(samples * window[:, None], axis=0)) ** 2, axis=1)
    frequencies = np.fft.rfftfreq(len(samples), 1 / rate)
    positive = power[1:] + 1e-30
    flatness = float(np.exp(np.mean(np.log(positive))) / np.mean(positive))
    return cast(Samples, frequencies), cast(Samples, power), flatness


class Regions:
    """Merge adjacent candidates without retaining per-window measurements."""

    def __init__(self) -> None:
        self.start: float | None = None
        self.end = 0.0
        self.value = 0.0

    def push(
        self, start: float, end: float, value: float, gap: float = 0
    ) -> tuple[float, float, float] | None:
        previous = None
        if self.start is not None and start > self.end + gap + 1e-9:
            previous = self.finish()
        if self.start is None:
            self.start, self.value = start, value
        self.end = end
        self.value = min(self.value, value)
        return previous

    def finish(self) -> tuple[float, float, float] | None:
        if self.start is None:
            return None
        value = (self.start, self.end, self.value)
        self.start = None
        return value
