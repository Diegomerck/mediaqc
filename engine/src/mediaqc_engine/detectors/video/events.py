"""Streaming duration/context gates. State size is independent of source length."""

from collections.abc import Iterator
from dataclasses import dataclass

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.detectors.common import number
from mediaqc_engine.detectors.contract import DetectorContext, DetectorResult
from mediaqc_engine.detectors.video.common import VideoDetector
from mediaqc_engine.detectors.video.features import Row, cache, rows, value


@dataclass
class Event:
    start: float
    end: float
    count: int
    first: Row
    minimum_similarity: float = 1.0
    before_motion: float = 0.0

    def extend(self, row: Row) -> None:
        self.end = value(row, "time") + value(row, "duration")
        self.count += 1
        self.minimum_similarity = min(self.minimum_similarity, value(row, "similarity"))


def sustained(
    source: Iterator[Row], kind: str, policy: dict[str, object]
) -> Iterator[Event]:
    event: Event | None = None
    for row in source:
        if kind in {"black_frame", "near_black_frame"}:
            ratio = (
                "black_pixel_ratio"
                if kind == "black_frame"
                else "near_black_pixel_ratio"
            )
            active = value(row, "mean_luma_normalized") <= number(
                policy, "max_mean_luma_normalized"
            ) and value(row, ratio) >= number(policy, "min_black_pixel_ratio")
        elif kind == "exposure_anomaly":
            active = max(
                value(row, "shadow_ratio"), value(row, "highlight_ratio")
            ) >= number(policy, "min_extreme_pixel_ratio")
        else:
            active = (
                value(row, "dominant_pixel_ratio")
                >= number(policy, "min_dominant_pixel_ratio")
                and value(row, "channel_spread_normalized")
                >= number(policy, "min_channel_spread_normalized")
                and value(row, "dominant_pixel_ratio") >= number(policy, "sensitivity")
            )
        if active:
            if event is None:
                event = Event(value(row, "time"), value(row, "time"), 0, row)
            event.extend(row)
        elif event is not None:
            yield event
            event = None
    if event is not None:
        yield event


def repeats(
    source: Iterator[Row], kind: str, policy: dict[str, object]
) -> Iterator[Event]:
    previous: Row | None = None
    event: Event | None = None
    pending: Event | None = None
    motion_count = 0
    after_count = 0
    required = int(str(policy.get("motion_context_frames", 1)))
    context_required = policy.get(
        "require_motion_context", policy.get("require_cadence_evidence", True)
    )
    before_valid = False
    for row in source:
        moving = value(row, "difference") >= number(policy, "min_surrounding_motion")
        if pending is not None:
            if moving:
                after_count += 1
                if after_count >= required:
                    yield pending
                    pending = None
            else:
                pending = None
        active = previous is not None and value(row, "similarity") >= number(
            policy, "similarity_threshold"
        )
        if kind == "freeze":
            active = active and value(row, "hash_similarity") >= number(
                policy, "hash_similarity_threshold"
            )
        if active and previous is not None:
            if event is None:
                before_valid = motion_count >= required
                event = Event(
                    value(previous, "time"),
                    value(previous, "time") + value(previous, "duration"),
                    1,
                    previous,
                    before_motion=value(previous, "difference"),
                )
            event.extend(row)
        elif event is not None:
            motion = min(event.before_motion, value(row, "difference"))
            event.first = {
                **event.first,
                "surrounding_motion": motion,
                "similarity": event.minimum_similarity,
            }
            if not context_required:
                yield event
            elif before_valid and moving:
                if required == 1:
                    yield event
                else:
                    pending, after_count = event, 1
            event = None
        motion_count = motion_count + 1 if moving else 0
        previous = row
    if event is not None and not context_required:
        event.first = {
            **event.first,
            "surrounding_motion": 0,
            "similarity": event.minimum_similarity,
        }
        yield event


def transients(
    source: Iterator[Row], kind: str, policy: dict[str, object]
) -> Iterator[Event]:
    previous: Row | None = None
    event: Event | None = None
    baseline = 0.0
    for row in source:
        luma = value(row, "mean_luma_normalized")
        if event is not None:
            if (
                value(row, "time") - event.start
                > number(policy, "max_duration_seconds") + 1e-9
            ):
                event = None
            elif abs(luma - baseline) <= number(policy, "return_tolerance_normalized"):
                # Visual corruption must also return in edge density, avoiding a
                # same-luma second cut being treated as a return to the old scene.
                if kind != "visual_anomaly" or abs(
                    value(row, "edge_density")
                    - value(event.first, "baseline_edge_density")
                ) <= number(policy, "return_tolerance_normalized"):
                    yield event
                    event = None
                else:
                    event.extend(row)
            else:
                event.extend(row)
        elif previous is not None:
            delta = abs(luma - value(previous, "mean_luma_normalized"))
            if kind == "visual_anomaly":
                active = (
                    value(row, "difference") >= number(policy, "min_frame_difference")
                    and value(row, "histogram_divergence")
                    >= number(policy, "min_histogram_divergence")
                    and value(row, "edge_density_delta")
                    >= number(policy, "min_edge_density_delta")
                    and max(
                        value(row, "histogram_divergence"),
                        value(row, "edge_density_delta"),
                    )
                    >= number(policy, "sensitivity")
                )
            else:
                active = delta >= number(policy, "min_luma_delta_normalized")
                if kind == "luminance_anomaly":
                    active = active and delta >= 1 - number(policy, "sensitivity")
            if active:
                baseline = value(previous, "mean_luma_normalized")
                event = Event(
                    value(row, "time"),
                    value(row, "time") + value(row, "duration"),
                    1,
                    {
                        **row,
                        "luma_delta_normalized": delta,
                        "baseline_edge_density": value(previous, "edge_density"),
                    },
                )
        previous = row


class EventDetector(VideoDetector):
    def measure(
        self, context: DetectorContext, stream: dict[str, object]
    ) -> DetectorResult:
        path, summary = cache(context, stream)
        if summary["errors"]:
            raise AppError(
                "MEDIA_UNSUPPORTED",
                "Video decode was incomplete; review integrity evidence",
                summary,
            )
        policy = self.policy(context)
        kind = self.detector_id.split(".")[1]
        source = rows(path, context)
        if kind in {"freeze", "duplicate_frame", "frame_cadence"}:
            events = repeats(source, kind, policy)
        elif kind in {"flash", "luminance_anomaly", "visual_anomaly"}:
            events = transients(source, kind, policy)
        else:
            events = sustained(source, kind, policy)
        result = DetectorResult(metrics=dict(summary))
        stream_start = max(0, float(str(stream.get("start_time_seconds") or 0)))
        duration = float(
            str(
                stream.get("duration_seconds")
                or context.media_asset.get("duration_seconds")
                or 0
            )
        )
        for event in events:
            seconds = event.end - event.start
            if seconds + 1e-9 < float(str(policy.get("min_duration_seconds", 0))):
                continue
            if (
                "max_duration_seconds" in policy
                and seconds > number(policy, "max_duration_seconds") + 1e-9
            ):
                continue
            if event.count < int(str(policy.get("min_repeat_count", 1))):
                continue
            head = float(str(policy.get("ignore_head_seconds", 0)))
            tail = float(str(policy.get("ignore_tail_seconds", 0)))
            if (head > 0 and event.start < stream_start + head) or (
                tail > 0 and duration > 0 and event.end > stream_start + duration - tail
            ):
                continue
            measurements: dict[str, object] = {
                **event.first,
                "duration_seconds": seconds,
                "frame_count": event.count,
                "similarity_statistic": event.minimum_similarity,
            }
            deterministic = kind in {"black_frame", "near_black_frame"}
            result.findings.append(
                self.finding(
                    context,
                    stream,
                    measurements,
                    "Video " + kind.replace("_", " ") + " candidate",
                    event.start,
                    event.end,
                    None if deterministic else 0.8,
                )
            )
        return result
