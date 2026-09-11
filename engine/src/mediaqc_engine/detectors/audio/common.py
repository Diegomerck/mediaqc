"""Profile lookup and canonical audio finding drafts."""

from typing import cast
from uuid import uuid4

from mediaqc_engine.detectors.contract import DetectorContext, DetectorResult
from mediaqc_engine.qc import profiles


def settings(profile: dict[str, object], detector_id: str) -> dict[str, object]:
    node: object = profile
    for part in detector_id.split("."):
        node = cast(dict[str, object], node)[part]
    return cast(dict[str, object], node)


def number(policy: dict[str, object], key: str) -> float:
    return float(str(policy[key]))


def pairs(policy: dict[str, object], channels: int) -> list[tuple[int, int]]:
    return [
        (a, b)
        for a, b in cast(list[list[int]], policy["pairs"])
        if a < channels and b < channels
    ]


class AudioDetector:
    detector_version = "1.0.0"

    def __init__(self, detector_id: str):
        self.detector_id = detector_id

    def supports(self, context: DetectorContext) -> bool:
        return any(s["stream_type"] == "audio" for s in context.streams)

    def policy(self, context: DetectorContext) -> dict[str, object]:
        # Legacy 1.0 snapshots retain all their thresholds. Added gates come from
        # the versioned distributed document and are included in finding thresholds.
        return {
            **settings(profiles.builtin(), self.detector_id),
            **settings(context.qc_profile, self.detector_id),
        }

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
        offset = max(0.0, float(str(stream.get("start_time_seconds") or 0)))
        return {
            "id": str(uuid4()),
            "detector_id": self.detector_id,
            "detector_version": self.detector_version,
            "stream_id": stream["id"],
            "severity": self.policy(context)["severity"],
            "confidence": confidence,
            "start_time_seconds": start + offset if start is not None else None,
            "end_time_seconds": end + offset if end is not None else None,
            "duration_seconds": end - start
            if start is not None and end is not None
            else None,
            "title": title,
            "description": title
            + "; review measured evidence against the selected profile.",
            "measurements": metrics,
            "threshold": self.policy(context),
            "evidence": [],
            "disposition": "OPEN",
            "metadata": {
                "profile_key": context.qc_profile["profile_key"],
                "profile_version": context.qc_profile["version"],
            },
        }

    def analyze(self, context: DetectorContext) -> DetectorResult:
        result = DetectorResult(metrics={"streams": {}})
        metrics = cast(dict[str, object], result.metrics["streams"])
        for stream in context.streams:
            context.cancellation.check()
            if stream["stream_type"] == "audio":
                part = self.measure(context, stream)
                metrics[str(stream["id"])] = part.metrics
                result.findings.extend(part.findings)
                result.warnings.extend(part.warnings)
        return result

    def measure(
        self, context: DetectorContext, stream: dict[str, object]
    ) -> DetectorResult:
        raise NotImplementedError
