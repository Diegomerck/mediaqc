"""System metadata only; unavailable later-phase features are explicit."""

import sys

from mediaqc_engine import __version__, ai
from mediaqc_engine.detectors import registry
from mediaqc_engine.media.tools import MediaTools

PROTOCOL_VERSION = "1.0"


def capabilities(provider: ai.Provider | None = None) -> dict[str, object]:
    return {
        "engine_version": __version__,
        "protocol_version": PROTOCOL_VERSION,
        "schema_version": 3,
        "batch": {
            "available": True,
            "contract_version": "1.0",
            "folder_extensions": [".wav", ".mp3", ".mp4", ".mxf"],
            "max_active_files": 1,
            "page_size": 50,
        },
        "platform": "windows" if sys.platform == "win32" else sys.platform,
        "ffmpeg": MediaTools().capability("ffmpeg"),
        "ffprobe": MediaTools().capability("ffprobe"),
        "ai": ai.capability(provider),
        "detectors": [
            {
                "id": detector.detector_id,
                "version": detector.detector_version,
                "media_types": [detector.detector_id.split(".")[0]],
                "requires_ai": False,
            }
            for detector in registry()
        ],
    }
