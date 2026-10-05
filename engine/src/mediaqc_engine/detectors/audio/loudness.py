"""FFmpeg EBU R128 metadata: K weighting, gating, LRA and oversampled true peak."""

import json
import math
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import cast

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.detectors.audio.common import AudioDetector, number
from mediaqc_engine.detectors.audio.dsp import Regions, db
from mediaqc_engine.detectors.audio.programs import programs, qualify
from mediaqc_engine.detectors.contract import DetectorContext, DetectorResult


def frames(
    context: DetectorContext, stream: dict[str, object], pad_tail: bool = False
) -> Iterator[dict[str, float]]:
    cache = (
        Path(context.work_dir)
        / f"r128-{'peak' if pad_tail else 'loudness'}-{stream['id']}.jsonl"
    )
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        with cache.open(encoding="utf-8") as source:
            for line in source:
                context.cancellation.check()
                yield json.loads(line)
        return
    partial = cache.with_suffix(".partial")
    rate = int(str(stream["sample_rate_hz"]))
    framing = (
        "apad=pad_dur=0.1,"
        if pad_tail
        else f"asetnsamples=n={max(1, round(rate / 10))}:p=1,"
    )
    arguments = [
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        str(context.media_asset["absolute_path"]),
        "-map",
        f"0:{stream['stream_index']}",
        "-vn",
        "-sn",
        "-dn",
        "-af",
        "asetpts=PTS-STARTPTS,"
        + framing
        + "ebur128=metadata=1:peak=true,ametadata=mode=print:file=-",
        "-f",
        "null",
        "-",
    ]
    if "_program_graph" in stream:
        arguments[0:0] = ["-threads", "1", "-filter_complex_threads", "1"]
        filter_start = arguments.index("-map")
        arguments[filter_start:] = [
            "-vn",
            "-sn",
            "-dn",
            "-filter_complex",
            str(stream["_program_graph"])
            + ",asetpts=PTS-STARTPTS,"
            + framing
            + "ebur128=metadata=1:peak=true,ametadata=mode=print:file=-[program]",
            "-map",
            "[program]",
            "-f",
            "null",
            "-",
        ]
    current: dict[str, float] = {}
    pending = b""
    try:
        with (
            partial.open("w", encoding="utf-8") as output,
            closing(context.media_tools.stream(arguments)) as chunks,
        ):
            for chunk in chunks:
                pending += chunk
                while b"\n" in pending:
                    raw_line, pending = pending.split(b"\n", 1)
                    text = raw_line.decode("utf-8").strip()
                    if text.startswith("frame:"):
                        if current:
                            output.write(json.dumps(current, allow_nan=False) + "\n")
                            yield current
                        current = {"time": float(text.split("pts_time:")[1])}
                        if round(current["time"] * 10) % 10 == 0:
                            context.report_progress(current["time"])
                    elif text.startswith("lavfi.r128."):
                        key, value = text.split("=", 1)
                        numeric = float(value)
                        if math.isfinite(numeric):
                            current[key.removeprefix("lavfi.r128.")] = numeric
            if "I" in current:
                output.write(json.dumps(current, allow_nan=False) + "\n")
                yield current
            else:
                raise AppError("MEDIA_UNSUPPORTED", "No EBU R128 frames decoded")
        partial.replace(cache)
    finally:
        partial.unlink(missing_ok=True)


class LoudnessDetector(AudioDetector):
    def __init__(self, detector_id: str):
        super().__init__(detector_id)
        if detector_id.startswith("audio.loudness."):
            self.detector_version = "1.1.0"

    def analyze(self, context: DetectorContext) -> DetectorResult:
        assignment = context.audio_assignment
        if assignment is None or self.detector_id == "audio.true_peak":
            return super().analyze(context)
        selected = programs(context)
        result = super().analyze(context)
        scopes = {
            str(s["id"]): {
                "kind": "stream",
                "members": [
                    [int(str(s["stream_index"])), c]
                    for c in range(int(str(s["channel_count"])))
                ],
            }
            for s in context.streams
            if s["stream_type"] == "audio"
        }
        for stream_id, measured in cast(
            dict[str, dict[str, object]], result.metrics["streams"]
        ).items():
            measured["measurement_scope"] = scopes[stream_id]
        for finding in result.findings:
            cast(dict[str, object], finding["measurements"])["measurement_scope"] = (
                scopes[str(finding["stream_id"])]
            )
            qualify(finding, assignment.identity, "UNASSIGNED_PROGRAM_SCOPE")
        program_metrics: dict[str, object] = {}
        result.metrics["programs"] = program_metrics
        result.metrics["applicability_policy"] = "explicit_audio_v1"
        if not selected:
            result.warnings.append({"code": "NO_DESIGNATED_AUDIO_PROGRAM"})
        for stream in selected:
            context.cancellation.check()
            part = self.measure(context, stream)
            part.metrics["measurement_scope"] = stream["measurement_scope"]
            program_metrics[str(stream["id"])] = part.metrics
            for finding in part.findings:
                finding["stream_id"] = None
                cast(dict[str, object], finding["measurements"])[
                    "measurement_scope"
                ] = stream["measurement_scope"]
                qualify(finding, assignment.identity, "APPLICABLE")
                finding["title"] = (
                    str(finding["title"])
                    + " (program "
                    + str(
                        cast(dict[str, object], stream["measurement_scope"])[
                            "program_id"
                        ]
                    )
                    + ")"
                )
            result.findings.extend(part.findings)
            result.warnings.extend(part.warnings)
        return result

    def measure(
        self, context: DetectorContext, stream: dict[str, object]
    ) -> DetectorResult:
        policy = self.policy(context)
        kind = self.detector_id.rsplit(".", 1)[-1]
        result = DetectorResult()
        region = Regions()
        last: dict[str, float] = {}
        maximum: float | None = None
        window = 3.0 if kind == "short_term" else 0.4
        key = "S" if kind == "short_term" else "M"
        duration = float(
            str(
                stream.get("duration_seconds")
                or context.media_asset.get("duration_seconds")
                or 0
            )
        )

        def event(value: tuple[float, float, float] | None) -> None:
            if value is None:
                return
            start, end, measured = value
            if end - start + 1e-9 >= number(policy, "min_event_duration_seconds"):
                result.findings.append(
                    self.finding(
                        context,
                        stream,
                        {
                            f"{kind}_lufs": measured,
                            "window_seconds": window,
                            "limit_lufs": policy["max_lufs"]
                            if policy["max_lufs"] is not None
                            and measured > number(policy, "max_lufs")
                            else policy.get("min_lufs"),
                        },
                        f"{kind.replace('_', ' ').title()} loudness outside bounds",
                        start,
                        end,
                    )
                )

        for frame in frames(context, stream, pad_tail=kind == "true_peak"):
            last = frame
            end = (
                min(frame["time"] + 0.1, duration) if duration else frame["time"] + 0.1
            )
            if kind not in {"short_term", "momentary"} or end + 1e-6 < window:
                continue
            value = frame[key]
            maximum = value if maximum is None else max(maximum, value)
            violated = (
                policy.get("max_lufs") is not None
                and value > number(policy, "max_lufs")
            ) or (
                policy.get("min_lufs") is not None
                and value < number(policy, "min_lufs")
            )
            if violated:
                event(region.push(frame["time"], end, value))
            else:
                event(region.finish())
        if kind in {"short_term", "momentary"}:
            event(region.finish())
            result.metrics = {
                f"{kind}_lufs": maximum,
                "window_seconds": window,
                "state": "MEASURED" if maximum is not None else "INSUFFICIENT_DURATION",
            }
            return result
        if kind == "true_peak":
            value = db(last.get("true_peak", 0))
            metrics: dict[str, object] = {
                "true_peak_dbtp": value,
                "per_channel_dbtp": {
                    k: db(v) for k, v in last.items() if k.startswith("true_peaks_ch")
                },
            }
            violated = policy["max_dbtp"] is not None and value > number(
                policy, "max_dbtp"
            )
        elif kind == "range":
            if duration and duration < 3:
                return DetectorResult(
                    metrics={
                        "loudness_range_lu": None,
                        "state": "INSUFFICIENT_DURATION",
                    }
                )
            value = last["LRA"]
            metrics = {"loudness_range_lu": value}
            violated = (
                policy["max_lu"] is not None and value > number(policy, "max_lu")
            ) or (policy["min_lu"] is not None and value < number(policy, "min_lu"))
        else:
            value = last["I"]
            # FFmpeg's -70 sentinel means no block survived the absolute R128 gate.
            if value <= -70:
                return DetectorResult(
                    metrics={"integrated_lufs": None, "state": "NO_GATED_AUDIO"},
                    warnings=[{"code": "NO_GATED_AUDIO", "stream_id": stream["id"]}],
                )
            metrics = {"integrated_lufs": value, "target_lufs": policy["target_lufs"]}
            violated = False
            if policy["target_lufs"] is not None:
                metrics["deviation_lu"] = value - number(policy, "target_lufs")
                violated = abs(value - number(policy, "target_lufs")) > number(
                    policy, "tolerance_lu"
                )
        result.metrics = metrics
        if violated:
            result.findings.append(
                self.finding(
                    context,
                    stream,
                    metrics,
                    f"{kind.replace('_', ' ').title()} outside profile bounds",
                )
            )
        return result
