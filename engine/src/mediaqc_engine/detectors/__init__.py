"""Production audio/video registry; scheduling remains in the job manager."""

from mediaqc_engine.detectors.audio import registry as audio_registry
from mediaqc_engine.detectors.contract import Detector
from mediaqc_engine.detectors.video import registry as video_registry


def registry() -> tuple[Detector, ...]:
    return (*audio_registry(), *video_registry())
