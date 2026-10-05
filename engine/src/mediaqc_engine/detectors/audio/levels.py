"""Sample peaks, clipping runs, silence and explicitly selected channel pairs."""

from typing import cast

import numpy as np

from mediaqc_engine.detectors.audio.common import AudioDetector, number, pairs
from mediaqc_engine.detectors.audio.dsp import Regions, correlation, db, rms, windows
from mediaqc_engine.detectors.contract import DetectorContext, DetectorResult
from mediaqc_engine.qc.audio_applicability import (
    applicability_severity,
    silence_applicability,
)


class LevelDetector(AudioDetector):
    def __init__(self, detector_id: str):
        super().__init__(detector_id)
        if detector_id == "audio.silence":
            self.detector_version = "1.1.0"

    def measure(
        self, context: DetectorContext, stream: dict[str, object]
    ) -> DetectorResult:
        policy = self.policy(context)
        kind = self.detector_id.rsplit(".", 1)[-1]
        channels = int(str(stream["channel_count"]))
        assignment = (
            getattr(context, "audio_assignment", None) if kind == "silence" else None
        )
        selected = (
            pairs(policy, channels)
            if kind in {"channel_imbalance", "phase_correlation"}
            else []
        )
        if kind in {"channel_imbalance", "phase_correlation"} and not selected:
            return DetectorResult(
                metrics={
                    "state": "NOT_APPLICABLE",
                    "reason": "No configured pair in this stream",
                }
            )
        result = DetectorResult()
        peak = np.zeros(channels)
        energy = np.zeros(channels)
        count = 0
        regions = [
            Regions() for _ in range(channels if assignment else max(1, len(selected)))
        ]
        clip_regions = [Regions() for _ in range(channels)]
        clip_counts, longest, previous_run = (
            [0] * channels,
            [0] * channels,
            [0] * channels,
        )
        end = 0.0
        phase_min = [1.0] * len(selected)
        phase_max = [-1.0] * len(selected)
        phase_count = [0] * len(selected)
        duration = float(
            str(
                stream.get("duration_seconds")
                or context.media_asset.get("duration_seconds")
                or 0
            )
        )

        def clipping(channel: int, region: tuple[float, float, float] | None) -> None:
            if region is not None and longest[channel] >= number(
                policy, "min_consecutive_samples"
            ):
                result.findings.append(
                    self.finding(
                        context,
                        stream,
                        {
                            "sample_peak_dbfs": db(-region[2]),
                            "clipped_sample_count": clip_counts[channel],
                            "max_consecutive_samples": longest[channel],
                            "channel_indices": [channel],
                        },
                        "Near-full-scale clipping evidence (audibility unconfirmed)",
                        region[0],
                        region[1],
                    )
                )
            clip_counts[channel], longest[channel], previous_run[channel] = 0, 0, 0

        def event(index: int, region: tuple[float, float, float] | None) -> None:
            if region is None:
                return
            start, finish, value = region
            if kind == "silence":
                if start < number(policy, "ignore_head_seconds") or (
                    duration
                    and number(policy, "ignore_tail_seconds") > 0
                    and finish > duration - number(policy, "ignore_tail_seconds")
                ):
                    return
                if finish - start + 1e-9 < number(policy, "min_duration_seconds"):
                    return
                metrics: dict[str, object] = {
                    "rms_dbfs": value,
                    "threshold_dbfs": policy["threshold_dbfs"],
                    "duration_seconds": finish - start,
                }
                title = "Silence below profile threshold"
            else:
                if finish - start + 1e-9 < number(policy, "min_event_duration_seconds"):
                    return
                metrics = {
                    "correlation_coefficient": value,
                    "window_seconds": 0.05,
                    "channel_indices": list(selected[index]),
                    "affected_duration_seconds": finish - start,
                }
                title = "Negative channel phase correlation"
            finding = self.finding(context, stream, metrics, title, start, finish)
            if assignment is not None:
                member = (int(str(stream["stream_index"])), index)
                state = silence_applicability(assignment, member)
                metrics["channel_indices"] = [index]
                metrics["measurement_scope"] = {
                    "kind": "channel",
                    "members": [list(member)],
                }
                metadata = cast(dict[str, object], finding["metadata"])
                metadata.update(
                    assignment_identity=assignment.identity,
                    applicability_policy="explicit_audio_v1",
                    applicability=state,
                    policy_severity=finding["severity"],
                )
                if state != "APPLICABLE":
                    finding["severity"] = applicability_severity(
                        state, str(finding["severity"])
                    )
                    finding["title"] = "Measured silence: " + state.lower().replace(
                        "_", " "
                    )
                    finding["description"] = (
                        "Measured channel silence retained; activity expectation is "
                        + state
                    )
            result.findings.append(finding)

        for start, samples, rate in windows(
            context, stream, 0.05 if kind == "phase_correlation" else 0.01
        ):
            end = start + len(samples) / rate
            peak = np.maximum(peak, np.max(np.abs(samples), axis=0))
            energy += np.sum(samples * samples, axis=0)
            count += len(samples)
            if kind == "silence":
                levels = (
                    [db(float(v)) for v in np.sqrt(np.mean(samples * samples, axis=0))]
                    if assignment
                    else [db(rms(samples))]
                )
                for index, level in enumerate(levels):
                    if level < number(policy, "threshold_dbfs"):
                        event(index, regions[index].push(start, end, level))
                    else:
                        event(index, regions[index].finish())
            elif kind == "phase_correlation":
                for index, (left, right) in enumerate(selected):
                    value = correlation(samples, left, right)
                    if value is not None:
                        phase_min[index] = min(phase_min[index], value)
                        phase_max[index] = max(phase_max[index], value)
                        phase_count[index] += 1
                    if (
                        value is not None
                        and policy["min_correlation"] is not None
                        and value < number(policy, "min_correlation")
                    ):
                        event(index, regions[index].push(start, end, value))
                    else:
                        event(index, regions[index].finish())
            elif kind == "clipping":
                for channel in range(channels):
                    mask = np.abs(samples[:, channel]) >= 10 ** (
                        number(policy, "near_full_scale_dbfs") / 20
                    )
                    edges = np.diff(np.r_[False, mask, False].astype(np.int8))
                    for begin, finish in zip(
                        np.flatnonzero(edges == 1),
                        np.flatnonzero(edges == -1),
                        strict=True,
                    ):
                        a, b = start + int(begin) / rate, start + int(finish) / rate
                        region = clip_regions[channel]
                        if (
                            region.start is not None
                            and a
                            > region.end + number(policy, "merge_gap_ms") / 1000 + 1e-9
                        ):
                            clipping(channel, region.finish())
                        adjacent = (
                            region.start is not None
                            and abs(a - region.end) < 0.5 / rate
                        )
                        length = int(finish - begin)
                        previous_run[channel] = length + (
                            previous_run[channel] if adjacent else 0
                        )
                        longest[channel] = max(longest[channel], previous_run[channel])
                        clip_counts[channel] += length
                        region.push(
                            a,
                            b,
                            -float(np.max(np.abs(samples[begin:finish, channel]))),
                            number(policy, "merge_gap_ms") / 1000,
                        )
        for index, region in enumerate(regions):
            if kind in {"silence", "phase_correlation"}:
                event(index, region.finish())
        if kind == "clipping":
            for channel, region in enumerate(clip_regions):
                clipping(channel, region.finish())
        channel_levels = [db(float(value)) for value in np.sqrt(energy / max(count, 1))]
        result.metrics = {
            "sample_peak_dbfs": [db(float(value)) for value in peak],
            "channel_rms_dbfs": channel_levels,
            "decoded_duration_seconds": end,
            "sample_count_per_channel": count,
        }
        if assignment is not None:
            result.metrics["audio_applicability"] = [
                {
                    "channel_index": i,
                    "state": silence_applicability(
                        assignment, (int(str(stream["stream_index"])), i)
                    ),
                }
                for i in range(channels)
            ]
        if kind == "phase_correlation":
            result.metrics["pairs"] = [
                {
                    "channel_indices": list(pair),
                    "minimum_correlation_coefficient": phase_min[index]
                    if phase_count[index]
                    else None,
                    "maximum_correlation_coefficient": phase_max[index]
                    if phase_count[index]
                    else None,
                    "measured_window_count": phase_count[index],
                    "window_seconds": 0.05,
                }
                for index, pair in enumerate(selected)
            ]
        if kind == "channel_imbalance":
            result.metrics["pairs"] = [
                {
                    "channel_indices": [left, right],
                    "difference_db": abs(channel_levels[left] - channel_levels[right]),
                }
                for left, right in selected
            ]
        if kind == "sample_peak":
            for channel, value in enumerate(peak):
                if policy["max_dbfs"] is not None and db(float(value)) > number(
                    policy, "max_dbfs"
                ):
                    result.findings.append(
                        self.finding(
                            context,
                            stream,
                            {
                                "sample_peak_dbfs": db(float(value)),
                                "channel": channel,
                            },
                            "Sample peak exceeds profile maximum",
                        )
                    )
        elif kind == "channel_imbalance":
            for left, right in selected:
                difference = abs(channel_levels[left] - channel_levels[right])
                if policy["max_difference_db"] is not None and difference > number(
                    policy, "max_difference_db"
                ):
                    result.findings.append(
                        self.finding(
                            context,
                            stream,
                            {
                                "channel_rms_dbfs": channel_levels,
                                "channel_indices": [left, right],
                                "difference_db": difference,
                            },
                            "Configured channels have unequal levels",
                        )
                    )
        return result
