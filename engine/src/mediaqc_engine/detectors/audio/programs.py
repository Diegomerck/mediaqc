"""Bounded decoded-frame clock validation and explicit unity-gain program routing."""

import hashlib
import json
from contextlib import closing
from fractions import Fraction
from pathlib import Path
from typing import cast

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.detectors.contract import DetectorContext
from mediaqc_engine.qc.audio_applicability import applicability_severity


def programs(context: DetectorContext) -> list[dict[str, object]]:
    assignment = context.audio_assignment
    assert assignment is not None
    physical = {
        int(str(s["stream_index"])): s
        for s in context.streams
        if s["stream_type"] == "audio"
    }
    selected = {s for p in assignment.programs for s, _ in p.members}
    if not selected:
        return []
    cache = Path(context.work_dir) / ("program-clock-" + assignment.identity + ".json")
    if cache.exists():
        timing: dict[str, list[float]] = json.loads(cache.read_text())
    else:
        count = dict.fromkeys(selected, 0)
        first: dict[int, Fraction] = {}
        try:
            rates = {i: int(str(physical[i]["sample_rate_hz"])) for i in selected}
            bases = {i: Fraction(str(physical[i]["time_base"])) for i in selected}
            if any(rates[i] <= 0 or bases[i] <= 0 for i in selected):
                raise ValueError("Invalid clock")
        except (ValueError, KeyError, ZeroDivisionError) as exc:
            raise AppError(
                "MEDIA_UNSUPPORTED", "Invalid program clock metadata"
            ) from exc
        pending = b""
        args = [
            "-protocol_whitelist",
            "file,pipe",
            "-threads",
            "1",
            "-select_streams",
            "a",
            "-show_frames",
            "-show_entries",
            "frame=stream_index,pts,nb_samples",
            "-of",
            "compact=p=0:nk=0",
            "-i",
            str(context.media_asset["absolute_path"]),
        ]
        with closing(
            context.media_tools.stream(args, tool="ffprobe", reject_errors=True)
        ) as chunks:
            for chunk in chunks:
                context.cancellation.check()
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    if len(line) > 4096:
                        raise AppError(
                            "MEDIA_UNSUPPORTED", "Program clock record exceeds bound"
                        )
                    values = dict(
                        item.split("=", 1)
                        for item in line.decode().strip().split("|")
                        if "=" in item
                    )
                    if "stream_index" not in values:
                        continue
                    index = int(values["stream_index"])
                    if index not in selected:
                        continue
                    try:
                        position = int(values["pts"]) * bases[index]
                        n = int(values["nb_samples"])
                        if n <= 0 or position < 0:
                            raise ValueError("Invalid frame")
                        first.setdefault(index, position)
                        if position != first[index] + Fraction(
                            count[index], rates[index]
                        ):
                            raise ValueError("Non-contiguous clock")
                        count[index] += n
                    except (KeyError, ValueError) as exc:
                        raise AppError(
                            "MEDIA_UNSUPPORTED",
                            "Program requires contiguous decoded sample clocks",
                        ) from exc
                if len(pending) > 4096:
                    raise AppError(
                        "MEDIA_UNSUPPORTED", "Program clock record exceeds bound"
                    )
        if pending.strip() or any(not count[i] for i in selected):
            raise AppError("MEDIA_UNSUPPORTED", "Incomplete program clock evidence")
        timing = {str(i): [float(first[i]), count[i] / rates[i]] for i in selected}
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(timing), encoding="utf-8")
    result = []
    for program in assignment.programs:
        members = program.members
        scopes = [timing[str(i)] for i, _ in members]
        rates_set = {int(str(physical[i]["sample_rate_hz"])) for i, _ in members}
        if len(rates_set) != 1 or any(s != scopes[0] for s in scopes[1:]):
            raise AppError(
                "MEDIA_UNSUPPORTED",
                "Program members have different decoded clocks or coverage",
            )
        rate = next(iter(rates_set))
        unique = list(dict.fromkeys(i for i, _ in members))
        if len(unique) == 1:
            graph = f"[0:{unique[0]}]pan={program.layout}|" + "|".join(
                f"c{k}=c{c}" for k, (_, c) in enumerate(members)
            )
        else:
            graph = (
                "".join(f"[0:{i}]" for i in unique)
                + f"join=inputs={len(unique)}:channel_layout={program.layout}:map="
                + "|".join(
                    f"{unique.index(i)}.{c}-{label}"
                    for (i, c), label in zip(members, ("FL", "FR"), strict=True)
                )
            )
        scope: dict[str, object] = {
            "kind": "program",
            "program_id": program.program_id,
            "layout": program.layout,
            "members": [list(m) for m in members],
            "assignment_identity": assignment.identity,
        }
        result.append(
            {
                "id": "program-"
                + hashlib.sha256(program.program_id.encode()).hexdigest(),
                "stream_type": "audio",
                "stream_index": members[0][0],
                "channel_count": len(members),
                "sample_rate_hz": rate,
                "start_time_seconds": scopes[0][0],
                "duration_seconds": scopes[0][1],
                "_program_graph": graph,
                "measurement_scope": scope,
            }
        )
    return result


def qualify(finding: dict[str, object], identity: str, state: str) -> None:
    metadata = cast(dict[str, object], finding["metadata"])
    metadata.update(
        assignment_identity=identity,
        applicability_policy="explicit_audio_v1",
        applicability=state,
        policy_severity=finding["severity"],
    )
    if state != "APPLICABLE":
        finding["severity"] = applicability_severity(state, str(finding["severity"]))
        finding["title"] = "Stream loudness measurement: program scope not evaluated"
        finding["description"] = (
            "Retained raw stream measurement; compliance uses "
            "explicitly mapped programs."
        )
