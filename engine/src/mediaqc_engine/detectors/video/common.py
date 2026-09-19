"""Video stream specialization; frame PTS already includes the stream offset."""

from mediaqc_engine.detectors.common import StreamDetector
from mediaqc_engine.detectors.contract import DetectorContext


class VideoDetector(StreamDetector):
    media_type = "video"

    def finding(
        self,
        context: DetectorContext,
        stream: dict[str, object],
        metrics: dict[str, object],
        title: str,
        start: float | None = None,
        end: float | None = None,
        confidence: float | None = None,
    ) -> dict[str, object]:
        return super().finding(
            context,
            {**stream, "start_time_seconds": 0},
            metrics,
            title,
            max(0, start) if start is not None else None,
            max(0, end) if end is not None else None,
            confidence,
        )
