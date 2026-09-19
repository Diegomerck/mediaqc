"""Deterministic decode, declared rate and original timestamp checks."""

from typing import cast

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.detectors.common import number
from mediaqc_engine.detectors.contract import DetectorContext, DetectorResult
from mediaqc_engine.detectors.video.common import VideoDetector
from mediaqc_engine.detectors.video.features import cache, rate, rows, value


class IntegrityDetector(VideoDetector):
    def measure(
        self, context: DetectorContext, stream: dict[str, object]
    ) -> DetectorResult:
        path, summary = cache(context, stream)
        policy = self.policy(context)
        result = DetectorResult(metrics=dict(summary))
        if self.detector_id == "video.decode_integrity":
            if summary["errors"]:
                context.logger.error(
                    "detector=%s decode errors=%s", self.detector_id, summary["errors"]
                )
                result.findings.append(
                    self.finding(
                        context,
                        stream,
                        summary,
                        "Video decode errors or incomplete decode",
                    )
                )
            return result
        if summary["errors"]:
            raise AppError(
                "MEDIA_UNSUPPORTED",
                "Video measurement is incomplete; inspect decode integrity evidence",
                summary,
            )
        expected = rate(stream.get("avg_frame_rate")) or rate(
            stream.get("real_frame_rate")
        )
        first: float | None = None
        previous: float | None = None
        minimum, maximum, total, count = float("inf"), 0.0, 0.0, 0
        for row in rows(path, context):
            pts = row["pts"]
            issues: list[str] = []
            interval = (
                pts - previous if pts is not None and previous is not None else None
            )
            if self.detector_id == "video.timestamp_integrity":
                if pts is None and policy["require_pts"]:
                    issues.append("MISSING_PTS")
                if (
                    pts is not None
                    and pts < 0
                    and not policy["allow_negative_timestamps"]
                ):
                    issues.append("NEGATIVE_PTS")
                if interval is not None:
                    if interval <= 0:
                        issues.append(
                            "DUPLICATE_PTS" if interval == 0 else "NON_MONOTONIC_PTS"
                        )
                    elif interval > number(policy, "max_gap_seconds"):
                        issues.append("ABNORMAL_INTERVAL")
                    elif (
                        expected
                        and not policy["allow_variable_frame_rate"]
                        and abs(interval * expected - 1)
                        > number(policy, "max_interval_deviation_ratio")
                    ):
                        issues.append("ABNORMAL_INTERVAL")
                if issues:
                    start = max(0, value(row, "time"))
                    end = start + value(row, "duration")
                    if (
                        result.findings
                        and result.findings[-1]["end_time_seconds"] == start
                    ):
                        last = result.findings[-1]
                        last["end_time_seconds"] = end
                        last["duration_seconds"] = end - float(
                            str(last["start_time_seconds"])
                        )
                        evidence = cast(dict[str, object], last["measurements"])
                        evidence["issues"] = sorted(
                            set(cast(list[str], evidence["issues"])) | set(issues)
                        )
                        evidence["affected_frame_count"] = (
                            int(str(evidence["affected_frame_count"])) + 1
                        )
                        evidence["last_pts_seconds"] = pts
                    else:
                        result.findings.append(
                            self.finding(
                                context,
                                stream,
                                {
                                    "issues": issues,
                                    "pts_seconds": pts,
                                    "previous_pts_seconds": previous,
                                    "interval_seconds": interval,
                                    "affected_frame_count": 1,
                                },
                                "Video timestamp integrity violation",
                                start,
                                end,
                            )
                        )
            if pts is not None:
                if first is None:
                    first = pts
                if interval is not None and interval > 0:
                    minimum = min(minimum, interval)
                    maximum = max(maximum, interval)
                    total += interval
                    count += 1
                previous = pts
        measured = count / total if total else None
        result.metrics.update(
            declared_average_fps=rate(stream.get("avg_frame_rate")),
            declared_real_fps=rate(stream.get("real_frame_rate")),
            measured_fps=measured,
            min_interval_seconds=minimum if count else None,
            max_interval_seconds=maximum if count else None,
        )
        if measured is None:
            result.warnings.append({"code": "INSUFFICIENT_TIMESTAMP_INTERVALS"})
        if self.detector_id == "video.frame_rate" and measured is not None:
            tolerance = number(policy, "tolerance_fps")
            cfr = maximum - minimum <= tolerance / (measured * measured) + 1e-9
            declared = [
                rate(stream.get(key)) for key in ("avg_frame_rate", "real_frame_rate")
            ]
            if (
                policy["compare_declared_rate"]
                and cfr
                and any(
                    fps is not None and abs(fps - measured) > tolerance + 1e-9
                    for fps in declared
                )
            ):
                result.findings.append(
                    self.finding(
                        context,
                        stream,
                        dict(result.metrics),
                        "Declared frame rate disagrees with constant decoded cadence",
                    )
                )
        if (
            self.detector_id == "video.frame_rate"
            and policy["expected_fps"] is not None
            and measured is not None
        ):
            target = number(policy, "expected_fps")
            if abs(measured - target) > number(policy, "tolerance_fps") + 1e-9:
                result.findings.append(
                    self.finding(
                        context,
                        stream,
                        dict(result.metrics),
                        "Measured video frame rate differs from profile expectation",
                    )
                )
        return result
