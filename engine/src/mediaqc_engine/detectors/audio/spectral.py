"""Spectral hum families and quiet-evidence-gated broadband noise estimates."""

import numpy as np

from mediaqc_engine.detectors.audio.common import AudioDetector, number
from mediaqc_engine.detectors.audio.dsp import db, rms, spectrum, windows
from mediaqc_engine.detectors.contract import DetectorContext, DetectorResult


class HumDetector(AudioDetector):
    def measure(
        self, context: DetectorContext, stream: dict[str, object]
    ) -> DetectorResult:
        policy = self.policy(context)
        fundamentals = policy["fundamentals_hz"]
        assert isinstance(fundamentals, list)
        counts = [0] * len(fundamentals)
        levels = [-300.0] * len(fundamentals)
        harmonics = [0] * len(fundamentals)
        starts: list[float | None] = [None] * len(fundamentals)
        ends = [0.0] * len(fundamentals)
        total = 0
        for start, samples, rate in windows(context, stream, 1.0, 0.5):
            if len(samples) < rate:
                continue
            total += 1
            frequencies, power, _ = spectrum(samples, rate)
            for index, fundamental in enumerate(fundamentals):
                detected, family = 0, 0.0
                for harmonic in range(1, int(number(policy, "harmonics")) + 1):
                    frequency = float(fundamental) * harmonic
                    if frequency >= rate / 2:
                        continue
                    distance = np.abs(frequencies - frequency)
                    band = distance <= number(policy, "frequency_tolerance_hz")
                    neighbors = (
                        distance > number(policy, "frequency_tolerance_hz") * 2
                    ) & (distance <= number(policy, "neighbor_band_hz"))
                    strength = float(np.sum(power[band]))
                    background = (
                        float(np.mean(power[neighbors])) * int(band.sum())
                        if neighbors.any()
                        else 0
                    )
                    relative = 10 * np.log10(
                        max(strength, 1e-30) / max(background, 1e-30)
                    )
                    if relative >= number(policy, "min_harmonic_prominence_db"):
                        detected += 1
                        family += strength
                level = float(
                    10 * np.log10(max(family, 1e-30) / max(float(power.sum()), 1e-30))
                )
                if (
                    detected >= number(policy, "min_harmonics_detected")
                    and level >= number(policy, "min_hum_level_db_relative")
                    and db(rms(samples)) >= number(policy, "activity_threshold_dbfs")
                ):
                    counts[index] += 1
                    levels[index] = max(levels[index], level)
                    harmonics[index] = max(harmonics[index], detected)
                    starts[index] = start if starts[index] is None else starts[index]
                    ends[index] = start + len(samples) / rate
        result = DetectorResult(metrics={"analyzed_window_count": total})
        for index, fundamental in enumerate(fundamentals):
            ratio = counts[index] / max(total, 1)
            if counts[index] and ratio >= number(policy, "min_persistence_ratio"):
                metrics: dict[str, object] = {
                    "fundamental_hz": fundamental,
                    "hum_level_db_relative": levels[index],
                    "harmonics_detected": harmonics[index],
                    "persistence_ratio": ratio,
                }
                result.findings.append(
                    self.finding(
                        context,
                        stream,
                        metrics,
                        "Persistent mains-frequency hum candidate",
                        starts[index],
                        ends[index],
                        min(1.0, ratio),
                    )
                )
        return result


class NoiseDetector(AudioDetector):
    def measure(
        self, context: DetectorContext, stream: dict[str, object]
    ) -> DetectorResult:
        policy = self.policy(context)
        # Fixed 0.1 dB histogram bounds quantization error and memory.
        histogram = np.zeros(3601, dtype=np.int64)
        for _, samples, _ in windows(context, stream, 0.1, 0.5):
            level = db(rms(samples))
            if policy["exclude_digital_silence"] and not np.any(samples):
                continue
            histogram[int(np.clip(round((level + 300) * 10), 0, 3600))] += 1
        rank = max(1, float(histogram.sum()) * number(policy, "quiet_percentile") / 100)
        cutoff = int(np.searchsorted(np.cumsum(histogram), rank)) / 10 - 300 + 0.05
        cutoff = min(cutoff, number(policy, "quiet_gate_dbfs"))
        count, sum_energy, sum_db, sum_db2, quiet_seconds = 0, 0.0, 0.0, 0.0, 0.0
        covered_end = 0.0
        for start, samples, rate in windows(context, stream, 0.1, 0.5):
            value = rms(samples)
            if (policy["exclude_digital_silence"] and not np.any(samples)) or db(
                value
            ) > cutoff:
                continue
            _, _, flatness = spectrum(samples, rate)
            if flatness < number(policy, "min_spectral_flatness"):
                continue
            end = start + len(samples) / rate
            quiet_seconds += max(0, end - max(start, covered_end))
            covered_end = end
            count += 1
            sum_energy += value * value
            sum_db += db(value)
            sum_db2 += db(value) ** 2
        deviation = float(
            np.sqrt(max(0, sum_db2 / max(count, 1) - (sum_db / max(count, 1)) ** 2))
        )
        sufficient = (
            count > 0
            and quiet_seconds + 1e-9 >= number(policy, "min_quiet_audio_seconds")
            and deviation <= number(policy, "max_quiet_std_db")
        )
        confidence = min(
            1.0, quiet_seconds / max(number(policy, "min_quiet_audio_seconds"), 0.05)
        ) / (1 + deviation)
        metrics: dict[str, object] = {
            "estimated_noise_floor_dbfs": db(float(np.sqrt(sum_energy / count)))
            if sufficient
            else None,
            "quiet_window_count": count,
            "quiet_audio_seconds": quiet_seconds,
            "confidence_basis": {
                "quiet_std_db": deviation,
                "spectral_flatness_gate": policy["min_spectral_flatness"],
                "percentile_cutoff_dbfs": cutoff,
            },
            "state": "MEASURED" if sufficient else "INSUFFICIENT_QUIET_REGIONS",
        }
        result = DetectorResult(metrics=metrics)
        if not sufficient:
            result.warnings.append(
                {"code": "INSUFFICIENT_QUIET_REGIONS", "stream_id": stream["id"]}
            )
        elif policy["max_estimated_noise_floor_dbfs"] is not None and float(
            str(metrics["estimated_noise_floor_dbfs"])
        ) > number(policy, "max_estimated_noise_floor_dbfs"):
            result.findings.append(
                self.finding(
                    context,
                    stream,
                    metrics,
                    "Estimated broadband noise floor exceeds profile maximum",
                    confidence=confidence,
                )
            )
        return result
