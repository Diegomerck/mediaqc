"""Phase 4 production registry, in master-spec implementation order."""

from mediaqc_engine.detectors.audio.levels import LevelDetector
from mediaqc_engine.detectors.audio.loudness import LoudnessDetector
from mediaqc_engine.detectors.audio.spectral import HumDetector, NoiseDetector
from mediaqc_engine.detectors.audio.transients import (
    DiscontinuityDetector,
    DropoutDetector,
)
from mediaqc_engine.detectors.contract import Detector


def registry() -> tuple[Detector, ...]:
    return (
        *(
            LoudnessDetector(f"audio.loudness.{kind}")
            for kind in ("integrated", "short_term", "momentary", "range")
        ),
        LoudnessDetector("audio.true_peak"),
        *(
            LevelDetector(f"audio.{kind}")
            for kind in (
                "sample_peak",
                "clipping",
                "silence",
                "channel_imbalance",
                "phase_correlation",
            )
        ),
        HumDetector("audio.hum"),
        NoiseDetector("audio.noise_floor"),
        DropoutDetector("audio.dropout"),
        DiscontinuityDetector("audio.discontinuity"),
    )
