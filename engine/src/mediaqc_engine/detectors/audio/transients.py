"""Contextual gap and confidence-scored isolated waveform jump candidates."""

from collections import deque

import numpy as np

from mediaqc_engine.detectors.audio.common import AudioDetector, number
from mediaqc_engine.detectors.audio.dsp import Regions, db, windows
from mediaqc_engine.detectors.contract import DetectorContext, DetectorResult


class GapState:
    """Bounded per-channel pre/gap/post evidence, independent of decode/UI."""

    def __init__(self, context_count: int):
        self.before: deque[float] = deque(maxlen=context_count)
        self.after: list[float] = []
        self.start: float | None = None
        self.end, self.pre, self.energy, self.count = 0.0, 0.0, 0.0, 0

    def feed(
        self, start: float, end: float, level: float, policy: dict[str, object]
    ) -> tuple[float, float, dict[str, object]] | None:
        result = None
        context_count = self.before.maxlen
        assert context_count is not None
        if db(float(np.sqrt(level))) < number(policy, "gap_threshold_dbfs"):
            if self.after:
                # A second gap without full intervening activity lacks pre-context.
                self.start = None
                self.before.clear()
                self.before.extend(self.after)
            if self.start is None:
                self.pre = (
                    float(np.mean(self.before))
                    if len(self.before) == context_count
                    else 0
                )
                self.start, self.energy, self.count = start, 0, 0
            self.end = end
            self.energy += level
            self.count += 1
            self.after.clear()
        elif self.start is not None:
            self.after.append(level)
            if len(self.after) >= context_count:
                duration = (self.end - self.start) * 1000
                pre = db(float(np.sqrt(self.pre)))
                post = db(float(np.sqrt(np.mean(self.after))))
                if number(policy, "min_duration_ms") - 1e-6 <= duration <= number(
                    policy, "max_duration_ms"
                ) + 1e-6 and min(pre, post) >= number(
                    policy, "activity_threshold_dbfs"
                ):
                    result = (
                        self.start,
                        self.end,
                        {
                            "pre_gap_rms_dbfs": pre,
                            "post_gap_rms_dbfs": post,
                            "gap_rms_dbfs": db(
                                float(np.sqrt(self.energy / self.count))
                            ),
                            "duration_ms": duration,
                            "context_ms": policy["context_ms"],
                        },
                    )
                self.start = None
                self.before.clear()
                self.before.extend(self.after)
                self.after.clear()
        else:
            self.before.append(level)
        return result


class DropoutDetector(AudioDetector):
    def measure(
        self, context: DetectorContext, stream: dict[str, object]
    ) -> DetectorResult:
        policy = self.policy(context)
        result = DetectorResult()
        states = [
            GapState(max(1, round(number(policy, "context_ms"))))
            for _ in range(int(str(stream["channel_count"])))
        ]
        for start, samples, rate in windows(context, stream, 0.001):
            for channel, level in enumerate(np.mean(samples * samples, axis=0)):
                event = states[channel].feed(
                    start, start + len(samples) / rate, float(level), policy
                )
                if event is not None:
                    begin, end, measurements = event
                    measurements["channel_indices"] = [channel]
                    result.findings.append(
                        self.finding(
                            context,
                            stream,
                            measurements,
                            "Short energy gap inside active audio",
                            begin,
                            end,
                            0.9,
                        )
                    )
        result.metrics = {
            "candidate_count": len(result.findings),
            "window_seconds": 0.001,
        }
        return result


class DiscontinuityDetector(AudioDetector):
    def measure(
        self, context: DetectorContext, stream: dict[str, object]
    ) -> DetectorResult:
        policy = self.policy(context)
        result = DetectorResult()
        region = Regions()
        previous: np.ndarray[tuple[int, ...], np.dtype[np.float64]] | None = None
        sensitivity = number(policy, "sensitivity")
        ratio_limit = number(policy, "min_derivative_ratio") * (2 - sensitivity)

        def event(value: tuple[float, float, float] | None) -> None:
            if value is not None:
                start, end, ratio = value
                result.findings.append(
                    self.finding(
                        context,
                        stream,
                        {
                            "derivative_ratio": -ratio,
                            "context_window_seconds": 0.02,
                            "sensitivity": sensitivity,
                        },
                        "Abrupt isolated waveform discontinuity candidate",
                        start,
                        end,
                        min(0.99, 0.5 + (-ratio / ratio_limit - 1) / 10),
                    )
                )

        for start, samples, rate in windows(context, stream, 0.02):
            padded = (
                np.concatenate((previous[None, :], samples))
                if previous is not None
                else np.concatenate((samples[:1], samples))
            )
            previous = samples[-1].copy()
            derivative = np.max(np.abs(np.diff(padded, axis=0)), axis=1)
            baseline = max(float(np.median(derivative)), 1e-12)
            indices = np.flatnonzero(
                (derivative >= number(policy, "min_jump_amplitude") * (2 - sensitivity))
                & (derivative / baseline >= ratio_limit)
            )
            for index in indices:
                time = start + int(index) / rate
                event(
                    region.push(
                        time,
                        time + 1 / rate,
                        -float(derivative[index] / baseline),
                        number(policy, "merge_gap_ms") / 1000,
                    )
                )
        event(region.finish())
        result.metrics = {
            "candidate_count": len(result.findings),
            "context_window_seconds": 0.02,
        }
        return result
