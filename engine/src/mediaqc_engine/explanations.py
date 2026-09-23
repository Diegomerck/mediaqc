"""Deterministic display adapters for saved findings; never evaluate QC policy."""

import math
from decimal import Decimal


def number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def explain(finding: dict[str, object]) -> dict[str, object]:
    metrics, policy = finding.get("measurements"), finding.get("threshold")
    fallback = {
        "summary": finding.get("description", "Review the saved measurements."),
        "comparisons": [],
    }
    if not isinstance(metrics, dict) or not isinstance(policy, dict):
        return fallback
    detector = finding.get("detector_id")
    mapping = {
        "audio.loudness.integrated": (
            "Integrated loudness",
            "integrated_lufs",
            "LUFS",
            "min_lufs",
            "max_lufs",
        ),
        "audio.loudness.range": (
            "Loudness range",
            "loudness_range_lu",
            "LU",
            "min_lu",
            "max_lu",
        ),
        "audio.true_peak": (
            "True peak",
            "true_peak_dbtp",
            "dBTP",
            "min_dbtp",
            "max_dbtp",
        ),
        "audio.sample_peak": (
            "Sample peak",
            "sample_peak_dbfs",
            "dBFS",
            "min_dbfs",
            "max_dbfs",
        ),
        "audio.channel_imbalance": (
            "Channel imbalance",
            "difference_db",
            "dB",
            "min_difference_db",
            "max_difference_db",
        ),
        "audio.phase_correlation": (
            "Phase correlation",
            "correlation_coefficient",
            "",
            "min_correlation",
            "max_correlation",
        ),
        "audio.noise_floor": (
            "Estimated noise floor",
            "estimated_noise_floor_dbfs",
            "dBFS",
            "min_estimated_noise_floor_dbfs",
            "max_estimated_noise_floor_dbfs",
        ),
        "audio.loudness.short_term": (
            "Short-term loudness",
            "short_term_lufs",
            "LUFS",
            "min_lufs",
            "max_lufs",
        ),
        "audio.loudness.momentary": (
            "Momentary loudness",
            "momentary_lufs",
            "LUFS",
            "min_lufs",
            "max_lufs",
        ),
        "video.frame_rate": (
            "Frame rate",
            "measured_fps",
            "fps",
            "min_fps",
            "max_fps",
        ),
    }
    if not isinstance(detector, str) or detector not in mapping:
        return fallback
    label, metric_key, unit, minimum_key, maximum_key = mapping[detector]
    measured = number(metrics.get(metric_key))
    low, high, target = (
        number(policy.get(minimum_key)),
        number(policy.get(maximum_key)),
        None,
    )
    if detector == "audio.loudness.integrated":
        target, tolerance = (
            number(policy.get("target_lufs")),
            number(policy.get("tolerance_lu")),
        )
        if target is not None and tolerance is not None:
            low, high = target - tolerance, target + tolerance
    elif detector == "video.frame_rate":
        target, tolerance = (
            number(policy.get("expected_fps")),
            number(policy.get("tolerance_fps")),
        )
        if target is not None and tolerance is not None:
            low, high = target - tolerance, target + tolerance
        else:
            return fallback  # Declared-rate/cadence comparisons are contextual.
    if measured is None:
        return fallback
    difference = None
    boundary = (
        low
        if low is not None and measured < low
        else high
        if high is not None and measured > high
        else None
    )
    if boundary is not None:
        difference = float(abs(Decimal(str(measured)) - Decimal(str(boundary))))
    elif low is not None or high is not None:
        difference = 0.0
    summary = (
        f"{label} is below the accepted range."
        if low is not None and measured < low
        else f"{label} is above the accepted limit."
        if high is not None and measured > high
        else str(fallback["summary"])
    )
    return {
        "summary": summary,
        "comparisons": [
            {
                "label": label,
                "measured": measured,
                "unit": unit,
                "target": target,
                "minimum": low,
                "maximum": high,
                "difference_from_limit": difference,
            }
        ],
    }
