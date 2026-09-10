"""Deterministic ffprobe metadata mapping and bounded source fingerprinting."""

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from mediaqc_engine.app.errors import AppError


def fingerprint(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as source:
            before = path.stat()
            digest = hashlib.sha256(f"{before.st_size}:{before.st_mtime_ns}:".encode())
            digest.update(source.read(4 * 1024 * 1024))
            source.seek(max(0, before.st_size - 4 * 1024 * 1024))
            digest.update(source.read(4 * 1024 * 1024))
            after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise AppError(
                "MEDIA_CHANGED",
                "Source changed during fingerprinting; inspect it again",
            )
        return {
            "absolute_path": str(path),
            "file_name": path.name,
            "file_size_bytes": before.st_size,
            "modified_at": datetime.fromtimestamp(before.st_mtime, UTC).isoformat(),
            "fast_fingerprint_sha256": digest.hexdigest(),
        }
    except FileNotFoundError as exc:
        raise AppError(
            "MEDIA_NOT_FOUND", "Source media was not found; choose another file"
        ) from exc
    except OSError as exc:
        raise AppError(
            "MEDIA_INSPECTION_FAILED", "Source media cannot be read"
        ) from exc


def text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def number(value: object) -> float | None:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except ValueError:
        return None


def integer(value: object) -> int | None:
    result = number(value)
    return (
        int(result)
        if result is not None and result >= 0 and result.is_integer()
        else None
    )


def map_probe(
    raw: dict[str, object],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    container, streams = raw.get("format"), raw.get("streams")
    if not isinstance(container, dict) or not isinstance(streams, list):
        raise AppError(
            "MEDIA_INSPECTION_FAILED", "Probe metadata is missing format or streams"
        )
    if not any(
        isinstance(item, dict) and item.get("codec_type") in {"audio", "video"}
        for item in streams
    ):
        raise AppError("MEDIA_UNSUPPORTED", "No audio or video streams were found")
    mapped: list[dict[str, object]] = []
    indices: set[int] = set()
    for stream in streams:
        if not isinstance(stream, dict):
            raise AppError(
                "MEDIA_INSPECTION_FAILED", "Probe stream metadata is malformed"
            )
        index = integer(stream.get("index"))
        if (
            index is None
            or index in indices
            or not isinstance(stream.get("codec_type"), str)
        ):
            raise AppError(
                "MEDIA_INSPECTION_FAILED", "Probe stream indices or types are invalid"
            )
        indices.add(index)
        tags = stream.get("tags", {})
        if not isinstance(tags, dict):
            tags = {}
        record: dict[str, object] = {
            "stream_index": index,
            "stream_type": stream["codec_type"],
            "language": text(tags.get("language")),
            "metadata_json": json.dumps(tags, allow_nan=False),
            "disposition_json": json.dumps(
                stream.get("disposition", {}), allow_nan=False
            ),
        }
        for target, origin in {
            "codec_name": "codec_name",
            "codec_long_name": "codec_long_name",
            "time_base": "time_base",
            "pixel_format": "pix_fmt",
            "color_space": "color_space",
            "color_transfer": "color_transfer",
            "color_primaries": "color_primaries",
            "field_order": "field_order",
            "avg_frame_rate": "avg_frame_rate",
            "real_frame_rate": "r_frame_rate",
            "channel_layout": "channel_layout",
            "sample_format": "sample_fmt",
        }.items():
            record[target] = text(stream.get(origin))
        for target, origin in {
            "width": "width",
            "height": "height",
            "sample_rate_hz": "sample_rate",
            "channel_count": "channels",
            "bit_rate": "bit_rate",
        }.items():
            record[target] = integer(stream.get(origin))
        record["duration_seconds"] = number(stream.get("duration"))
        record["start_time_seconds"] = number(stream.get("start_time"))
        mapped.append(record)
    return {
        "container_format": text(container.get("format_name")),
        "duration_seconds": number(container.get("duration")),
        "ffprobe_json": json.dumps(raw, allow_nan=False),
    }, mapped
