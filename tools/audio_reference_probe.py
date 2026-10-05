"""Read-only Phase 12 audio measurements; no reference defect adjudication."""

import argparse
import json
from contextlib import closing
from pathlib import Path
from typing import Any, cast

import numpy as np
from detector_acceptance import artifact_path, digest
from numpy.typing import NDArray

from mediaqc_engine.detectors.common import settings
from mediaqc_engine.media.inspection import fingerprint
from mediaqc_engine.media.tools import MediaTools
from mediaqc_engine.qc.profiles import builtin

RATE = 48000


def transient_metrics(samples: NDArray[np.float64]) -> dict[str, object]:
    """One bounded mono excerpt, starting on a production 20 ms boundary."""
    if samples.ndim != 1 or not 960 <= len(samples) <= RATE // 2:
        raise ValueError("Require 20-500 ms of mono 48 kHz samples")
    policy = settings(builtin(), "audio.discontinuity")
    scale = 2 - float(str(policy["sensitivity"]))
    jump_limit = float(str(policy["min_jump_amplitude"])) * scale
    ratio_limit = float(str(policy["min_derivative_ratio"])) * scale
    derivative = np.abs(np.diff(samples, prepend=samples[0]))
    windows = []
    for start in range(960, len(samples) - 959, 960):
        # Skip the initial block: its preceding sample is intentionally absent.
        block = samples[start : start + 960]
        delta = derivative[start : start + 960]
        baseline = max(float(np.median(delta)), 1e-12)
        hit = np.flatnonzero((delta >= jump_limit) & (delta / baseline >= ratio_limit))
        power = (
            np.abs(np.fft.rfft((block - block.mean()) * np.hanning(len(block)))) ** 2
        )
        frequency = np.fft.rfftfreq(len(block), 1 / RATE)
        windows.append(
            {
                "offset_seconds": start / RATE,
                "rms": float(np.sqrt(np.mean(block * block))),
                "mean": float(block.mean()),
                "max_jump": float(delta.max()),
                "median_derivative": baseline,
                "max_derivative_ratio": float(delta.max() / baseline),
                "candidate_sample_count": len(hit),
                "first_candidate_offset": (start + int(hit[0])) / RATE
                if len(hit)
                else None,
                "last_candidate_offset": (start + int(hit[-1])) / RATE
                if len(hit)
                else None,
                "energy_fraction_above_8khz": float(
                    power[frequency >= 8000].sum() / power.sum()
                )
                if power.sum()
                else None,
            }
        )
    return {"jump_limit": jump_limit, "ratio_limit": ratio_limit, "windows": windows}


def excerpt(tools: MediaTools, source: Path, index: int) -> NDArray[np.float64]:
    # Exact sample coordinates preserve the detector's 20 ms window alignment.
    start, count = 360000, 8640  # 7.50-7.68 s, at 48 kHz
    data = bytearray()
    with closing(
        tools.stream(
            [
                "-protocol_whitelist",
                "file",
                "-i",
                str(source),
                "-map",
                f"0:{index}",
                "-vn",
                "-sn",
                "-dn",
                "-af",
                f"atrim=start_sample={start}:end_sample={start + count},"
                "asetpts=PTS-STARTPTS",
                "-t",
                str(count / RATE),
                "-c:a",
                "pcm_f64le",
                "-f",
                "f64le",
                "pipe:1",
            ],
            reject_errors=True,
        )
    ) as chunks:
        for chunk in chunks:
            if len(data) + len(chunk) > count * 8:
                raise ValueError("Excerpt exceeded mono sample bound")
            data.extend(chunk)
    if len(data) != count * 8:
        raise ValueError("Incomplete audio excerpt")
    return np.frombuffer(data, dtype="<f8")


def program_loudness(tools: MediaTools, source: Path, graph: str) -> dict[str, float]:
    # Explicit read-only program mapping; no derived media file or runtime policy.
    graph += (
        ",asetnsamples=n=4800:p=1,ebur128=metadata=1:peak=true,"
        "ametadata=mode=print:file=-[out]"
    )
    latest: dict[str, float] = {}
    pending = b""
    with closing(
        tools.stream(
            [
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(source),
                "-filter_complex",
                graph,
                "-map",
                "[out]",
                "-vn",
                "-sn",
                "-dn",
                "-f",
                "null",
                "-",
            ],
            reject_errors=True,
        )
    ) as chunks:
        for chunk in chunks:
            pending += chunk
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                if line.startswith(b"lavfi.r128."):
                    key, value = line.decode().split("=")
                    latest[key.removeprefix("lavfi.r128.")] = float(value)
            if len(pending) > 65536:
                raise ValueError("Oversized loudness metadata line")
    if "I" not in latest:
        raise ValueError("No loudness measurement")
    return latest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = artifact_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(args.manifest.read_text())
    report: dict[str, object] = {
        "note": "Developer measurements only; MXF transient intent remains unresolved."
    }
    for reference in manifest["references"]:
        name = reference["reference_id"]
        if name not in {"wav_test_1", "mxf_test_1"}:
            continue
        source = Path(reference["source"])
        if (
            fingerprint(source)["fast_fingerprint_sha256"]
            != reference["fast_fingerprint_sha256"]
        ):
            raise ValueError("Reference identity changed")
        before = digest(source), source.stat().st_size, source.stat().st_mtime_ns
        tools = MediaTools(cache=output.parent)
        item: dict[str, object] = {"source_sha256": before[0]}
        try:
            streams = cast(list[dict[str, Any]], tools.probe(source)["streams"])
            audio = [s for s in streams if s["codec_type"] == "audio"]
            if any(int(s["sample_rate"]) != RATE for s in audio):
                raise ValueError("Reference sample rate differs from declared recipe")
            if name == "wav_test_1":
                if (
                    len(audio) != 1
                    or audio[0]["channels"] != 7
                    or audio[0]["index"] != 0
                ):
                    raise ValueError("Unexpected WAV layout")
                graph = "[0:0]pan=stereo|c0=c0|c1=c1,asetpts=PTS-STARTPTS"
            else:
                if [s["index"] for s in audio] != list(range(1, 9)) or any(
                    s["channels"] != 1 or float(s.get("start_time", 0)) != 0
                    for s in audio
                ):
                    raise ValueError("Unexpected MXF stream layout/alignment")
                left, right = excerpt(tools, source, 1), excerpt(tools, source, 2)
                item["excerpt_start_seconds"] = 7.5
                item["streams"] = {
                    "1": transient_metrics(left),
                    "2": transient_metrics(right),
                }
                # Lag comparison across the same 20 ms event window, ±2 ms.
                a, b = left[2880:3840], right[2880:3840]
                correlations = []
                for lag in range(-96, 97):
                    x, y = (
                        (a[:lag], b[-lag:]) if lag < 0 else (a[lag:], b[: len(b) - lag])
                    )
                    x, y = x - x.mean(), y - y.mean()
                    norm = np.linalg.norm(x) * np.linalg.norm(y)
                    correlations.append(float(np.dot(x, y) / norm) if norm else 0)
                best = int(np.argmax(np.abs(correlations)))
                item["event_correlation"] = {
                    "zero_lag": correlations[96],
                    "best_signed": correlations[best],
                    "left_relative_lag_samples": best - 96,
                    "search_radius_samples": 96,
                }
                graph = (
                    "[0:1][0:2]join=inputs=2:channel_layout=stereo:map=0.0-FL|1.0-FR,"
                    "asetpts=PTS-STARTPTS"
                )
            item["program_mapping"] = graph
            item["program_r128"] = program_loudness(tools, source, graph)
        finally:
            tools.cancel()
            if before != (
                digest(source),
                source.stat().st_size,
                source.stat().st_mtime_ns,
            ):
                raise AssertionError("Source changed")
        report[name] = item
    output.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
