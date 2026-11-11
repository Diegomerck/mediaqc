"""Read-only built-in profile needed to select and snapshot a run."""

import json
import re
from pathlib import Path

from mediaqc_engine.app.errors import AppError


def _raw(key: str, version: str) -> dict[str, object]:
    filename: str | None = None
    if key == "editorial_rushes" and version == "1.0.0":
        filename = "editorial_rushes_1_0.json"
    elif key == "general_technical_qc":
        if version == "1.0.0":
            filename = "general_technical_qc_1_0.json"
        elif version == "1.1.0":
            filename = "general_technical_qc_1_1.json"
        elif version == "1.2.0":
            filename = "general_technical_qc.json"
    if filename is None:
        raise AppError("PROFILE_NOT_FOUND", "Choose an available profile version")
    path = Path(__file__).with_name(filename)
    if not path.is_file():
        raise AppError("PROFILE_NOT_FOUND", "Choose an available profile version")
    value: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return value


def builtin(version: str = "1.2.0") -> dict[str, object]:
    return _raw("general_technical_qc", version)


def validate(profile: dict[str, object]) -> None:
    key = str(profile.get("profile_key"))
    ver = str(profile.get("version"))
    if key == "editorial_rushes" and ver == "1.0.0":
        baseline = _raw("editorial_rushes", "1.0.0")
    else:
        baseline = builtin(ver)

    def check(value: object, template: object) -> None:
        if isinstance(template, dict):
            if not isinstance(value, dict) or not template.keys() <= value.keys():
                raise AppError(
                    "PROFILE_INVALID", "Profile is missing required settings"
                )
            for key, item in template.items():
                nullable_bound = key in {
                    "target_lufs",
                    "max_dbtp",
                    "max_dbfs",
                    "max_estimated_noise_floor_dbfs",
                    "max_difference_db",
                    "min_correlation",
                }
                if not (nullable_bound and value[key] is None):
                    check(value[key], item)
                setting = value[key]
                if key == "severity" and setting not in {"INFO", "WARN", "FAIL"}:
                    raise AppError("PROFILE_INVALID", "Invalid severity")
                if isinstance(setting, (int, float)):
                    if (
                        any(
                            unit in key
                            for unit in (
                                "seconds",
                                "duration_ms",
                                "count",
                                "samples",
                                "pairs",
                            )
                        )
                        and setting < 0
                    ):
                        raise AppError(
                            "PROFILE_INVALID",
                            "Durations and counts must be non-negative",
                        )
                    if (
                        (key.endswith("_ratio") and key != "min_derivative_ratio")
                        or key.endswith("_normalized")
                        or key.endswith("similarity_threshold")
                        or key
                        in {
                            "min_frame_difference",
                            "min_histogram_divergence",
                            "min_edge_density_delta",
                            "min_surrounding_motion",
                        }
                        or key == "sensitivity"
                        or key.endswith("_percentile")
                    ):
                        limit = 100 if "percentile" in key else 1
                        if not 0 <= setting <= limit:
                            raise AppError(
                                "PROFILE_INVALID",
                                "Profile setting is outside its range",
                            )
            for low, high in (
                ("min_lufs", "max_lufs"),
                ("min_lu", "max_lu"),
                ("min_duration_ms", "max_duration_ms"),
                ("min_duration_seconds", "max_duration_seconds"),
                ("shadow_luma_normalized", "highlight_luma_normalized"),
            ):
                if (
                    value.get(low) is not None
                    and value.get(high) is not None
                    and value[low] > value[high]
                ):
                    raise AppError("PROFILE_INVALID", "Minimum must not exceed maximum")
            for dimension in ("width", "height"):
                if dimension in value and (
                    type(value[dimension]) is not int
                    or not 16 <= value[dimension] <= 1920
                ):
                    raise AppError(
                        "PROFILE_INVALID",
                        "Video dimensions must be integers in [16,1920]",
                    )
            if value.get("expected_fps") is not None and value["expected_fps"] <= 0:
                raise AppError(
                    "PROFILE_INVALID", "Expected frame rate must be positive"
                )
            for key in ("pairs",):
                if key in value and (
                    not value[key]
                    or any(
                        not isinstance(pair, list)
                        or len(pair) != 2
                        or any(type(index) is not int or index < 0 for index in pair)
                        or pair[0] == pair[1]
                        for pair in value[key]
                    )
                ):
                    raise AppError(
                        "PROFILE_INVALID",
                        "Channel pairs require two distinct non-negative indices",
                    )
            for key in (
                "min_consecutive_samples",
                "harmonics",
                "min_harmonics_detected",
                "min_repeat_count",
                "motion_context_frames",
            ):
                if key in value and (type(value[key]) is not int or value[key] < 1):
                    raise AppError(
                        "PROFILE_INVALID",
                        "Sample and harmonic counts must be positive integers",
                    )
            if "fundamentals_hz" in value and (
                not value["fundamentals_hz"]
                or any(
                    type(f) not in (int, float) or f <= 0
                    for f in value["fundamentals_hz"]
                )
            ):
                raise AppError("PROFILE_INVALID", "Hum frequencies must be positive")
            for key in (
                "merge_gap_ms",
                "tolerance_lu",
                "tolerance_fps",
                "max_difference_db",
                "max_quiet_std_db",
                "min_jump_amplitude",
                "min_derivative_ratio",
            ):
                if key in value and value[key] is not None and value[key] < 0:
                    raise AppError("PROFILE_INVALID", "Gate must be non-negative")
            if (
                value.get("min_correlation") is not None
                and not -1 <= value["min_correlation"] <= 1
            ):
                raise AppError("PROFILE_INVALID", "Correlation must be in [-1,1]")
            if (
                "min_spectral_flatness" in value
                and not 0 <= value["min_spectral_flatness"] <= 1
            ):
                raise AppError("PROFILE_INVALID", "Flatness must be in [0,1]")
            for key in ("context_ms", "frequency_tolerance_hz", "neighbor_band_hz"):
                if key in value and value[key] <= 0:
                    raise AppError("PROFILE_INVALID", "Window sizes must be positive")
        elif isinstance(template, bool):
            if not isinstance(value, bool):
                raise AppError("PROFILE_INVALID", "Enabled settings must be boolean")
        elif isinstance(template, str):
            if not isinstance(value, str) or not value:
                raise AppError("PROFILE_INVALID", "Profile text must not be empty")
        elif isinstance(template, (int, float)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise AppError("PROFILE_INVALID", "Profile threshold must be numeric")
        elif isinstance(template, list) and not isinstance(value, list):
            raise AppError("PROFILE_INVALID", "Profile setting must be an array")
        elif template is None and value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise AppError("PROFILE_INVALID", "A bound must be numeric or null")

    check(profile, baseline)

    def merged(
        defaults: dict[str, object], supplied: dict[str, object]
    ) -> dict[str, object]:
        result = dict(defaults)
        for key, item in supplied.items():
            default = defaults.get(key)
            result[key] = (
                merged(default, item)
                if isinstance(default, dict) and isinstance(item, dict)
                else item
            )
        return result

    # Validate optional Phase 4 gates even on a legacy snapshot, without mutating it.
    check(merged(builtin(), profile), builtin())
    if profile["schema_version"] != "1.0.0":
        raise AppError("PROFILE_INVALID", "Unsupported profile schema")
    if re.fullmatch(r"[a-z0-9_.-]+", str(profile["profile_key"])) is None:
        raise AppError("PROFILE_INVALID", "Invalid profile key")
    try:
        json.dumps(profile, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise AppError(
            "PROFILE_INVALID", "Profile must contain finite JSON values"
        ) from exc


def get(key: object, version: object) -> dict[str, object]:
    if not isinstance(key, str) or not isinstance(version, str):
        raise AppError("PROFILE_NOT_FOUND", "Choose an available profile version")
    profile = _raw(key, version)
    validate(profile)
    return profile


def available() -> list[dict[str, object]]:
    return [
        {
            field: profile[field]
            for field in ("profile_key", "name", "version", "description")
        }
        for profile in (
            get("editorial_rushes", "1.0.0"),
            get("general_technical_qc", "1.2.0"),
        )
    ]


def enabled(profile: dict[str, object], detector_id: str) -> bool:
    node: object = profile
    for part in detector_id.split("."):
        if not isinstance(node, dict) or node.get("enabled") is False:
            return False
        node = node.get(part)
    return isinstance(node, dict) and node.get("enabled") is True
