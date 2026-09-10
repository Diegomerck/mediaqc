"""System metadata only; unavailable later-phase features are explicit."""

import sys

from mediaqc_engine import __version__

PROTOCOL_VERSION = "1.0"


def capabilities() -> dict[str, object]:
    return {
        "engine_version": __version__,
        "protocol_version": PROTOCOL_VERSION,
        "schema_version": 1,
        "platform": "windows" if sys.platform == "win32" else sys.platform,
        "ffmpeg": {"available": False, "version": None},
        "ffprobe": {"available": False, "version": None},
        "ai": {"local_available": False, "provider": None},
        "detectors": [],
    }
