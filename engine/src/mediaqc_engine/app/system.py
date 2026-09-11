"""System metadata only; unavailable later-phase features are explicit."""

import sys

from mediaqc_engine import __version__
from mediaqc_engine.detectors.audio import registry
from mediaqc_engine.media.tools import MediaTools

PROTOCOL_VERSION = "1.0"


def capabilities() -> dict[str, object]:
    return {
        "engine_version": __version__,
        "protocol_version": PROTOCOL_VERSION,
        "schema_version": 1,
        "platform": "windows" if sys.platform == "win32" else sys.platform,
        "ffmpeg": MediaTools().capability("ffmpeg"),
        "ffprobe": MediaTools().capability("ffprobe"),
        "ai": {"local_available": False, "provider": None},
        "detectors": [
            {
                "id": detector.detector_id,
                "version": detector.detector_version,
                "media_types": ["audio"],
                "requires_ai": False,
            }
            for detector in registry()
        ],
    }
