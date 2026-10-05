"""UI-free scheduling contract from the detector specification."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from mediaqc_engine.jobs.cancellation import CancellationToken
from mediaqc_engine.media.tools import MediaTools
from mediaqc_engine.qc.audio_applicability import Snapshot


@dataclass(frozen=True)
class DetectorContext:
    analysis_run_id: str
    media_asset: dict[str, object]
    streams: tuple[dict[str, object], ...]
    qc_profile: dict[str, object]
    work_dir: str
    cancellation: CancellationToken
    media_tools: MediaTools
    logger: logging.LoggerAdapter[logging.Logger]
    report_progress: Callable[[float], None] = lambda seconds: None
    audio_assignment: Snapshot | None = None


@dataclass
class DetectorResult:
    findings: list[dict[str, object]] = field(default_factory=list)
    metrics: dict[str, object] = field(default_factory=dict)
    warnings: list[dict[str, object]] = field(default_factory=list)


class Detector(Protocol):
    detector_id: str
    detector_version: str

    def supports(self, context: DetectorContext) -> bool: ...
    def analyze(self, context: DetectorContext) -> DetectorResult: ...
