"""Phase 5 registry in master-spec order."""

from mediaqc_engine.detectors.contract import Detector
from mediaqc_engine.detectors.video.events import EventDetector
from mediaqc_engine.detectors.video.integrity import IntegrityDetector


def registry() -> tuple[Detector, ...]:
    return (
        *(
            IntegrityDetector("video." + kind)
            for kind in ("decode_integrity", "frame_rate", "timestamp_integrity")
        ),
        *(
            EventDetector("video." + kind)
            for kind in (
                "black_frame",
                "near_black_frame",
                "freeze",
                "duplicate_frame",
                "frame_cadence",
                "luminance_anomaly",
                "flash",
                "exposure_anomaly",
                "color_anomaly",
                "visual_anomaly",
            )
        ),
    )
