"""Read-only built-in profile needed to select and snapshot a run."""

import json
import re
from pathlib import Path

from mediaqc_engine.app.errors import AppError


def builtin() -> dict[str, object]:
    value: dict[str, object] = json.loads(
        Path(__file__)
        .with_name("general_technical_qc.json")
        .read_text(encoding="utf-8")
    )
    return value


def validate(profile: dict[str, object]) -> None:
    baseline = builtin()

    def check(value: object, template: object) -> None:
        if isinstance(template, dict):
            if not isinstance(value, dict) or not template.keys() <= value.keys():
                raise AppError(
                    "PROFILE_INVALID", "Profile is missing required settings"
                )
            for key, item in template.items():
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
                        key.endswith("_ratio")
                        or key == "sensitivity"
                        or key.endswith("_percentile")
                    ):
                        limit = 100 if "percentile" in key else 1
                        if not 0 <= setting <= limit:
                            raise AppError(
                                "PROFILE_INVALID",
                                "Profile setting is outside its range",
                            )
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
    profile = builtin()
    if key != profile["profile_key"] or version != profile["version"]:
        raise AppError("PROFILE_NOT_FOUND", "Choose an available profile version")
    validate(profile)
    return profile


def enabled(profile: dict[str, object], detector_id: str) -> bool:
    node: object = profile
    for part in detector_id.split("."):
        if not isinstance(node, dict) or node.get("enabled") is False:
            return False
        node = node.get(part)
    return isinstance(node, dict) and node.get("enabled") is True
