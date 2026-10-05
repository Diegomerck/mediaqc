"""Reject ambiguous/misaligned program clocks instead of silently repairing them."""

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.detectors.audio.programs import programs
from mediaqc_engine.detectors.contract import DetectorContext
from mediaqc_engine.jobs.cancellation import CancellationToken
from mediaqc_engine.qc.audio_applicability import parse_contract


def context(
    tmp_path: Path, payload: bytes, second_rate: int = 48000
) -> tuple[DetectorContext, list[bool]]:
    doc = {
        "schema_version": "0.1.0",
        "source_sha256": "a" * 64,
        "provenance": "test",
        "channels": [
            {"member": [i, 0], "role": "mix", "expectation": "expected"} for i in (1, 2)
        ],
        "programs": [
            {"program_id": "mix", "layout": "stereo", "members": [[1, 0], [2, 0]]}
        ],
    }
    closed: list[bool] = []

    def stream(*args: object, **kwargs: object) -> Iterator[bytes]:
        try:
            # Split mid-record to exercise bounded incremental parsing.
            yield payload[:13]
            yield payload[13:]
        finally:
            closed.append(True)

    ctx = cast(
        DetectorContext,
        SimpleNamespace(
            audio_assignment=parse_contract(doc, {1: 1, 2: 1}, "a" * 64),
            streams=tuple(
                {
                    "stream_index": i,
                    "stream_type": "audio",
                    "sample_rate_hz": 48000 if i == 1 else second_rate,
                    "time_base": "1/48000",
                    "channel_count": 1,
                }
                for i in (1, 2)
            ),
            work_dir=str(tmp_path),
            media_asset={"absolute_path": "synthetic-only"},
            cancellation=CancellationToken(),
            media_tools=SimpleNamespace(stream=stream),
        ),
    )
    return ctx, closed


@pytest.mark.parametrize(
    "payload,rate",
    [
        (
            b"stream_index=1|pts=0|nb_samples=960\nstream_index=2|pts=1|nb_samples=960\n",
            48000,
        ),
        (
            b"stream_index=1|pts=0|nb_samples=960\nstream_index=2|pts=0|nb_samples=480\n",
            48000,
        ),
        (
            b"stream_index=1|pts=0|nb_samples=960\nstream_index=1|pts=961|nb_samples=960\n",
            48000,
        ),
        (b"stream_index=1|pts=N/A|nb_samples=960\n", 48000),
        (b"stream_index=1|pts=0|nb_samples=960\n", 48000),
        (b"x" * 4097, 48000),
        (
            b"stream_index=1|pts=0|nb_samples=960\nstream_index=2|pts=0|nb_samples=960\n",
            44100,
        ),
    ],
)
def test_program_clock_rejection(tmp_path: Path, payload: bytes, rate: int) -> None:
    ctx, closed = context(tmp_path, payload, rate)
    with pytest.raises(AppError):
        programs(ctx)
    assert closed == [True]


def test_program_clock_validation_is_reused(tmp_path: Path) -> None:
    ctx, closed = context(
        tmp_path,
        b"stream_index=1|pts=0|nb_samples=960\nstream_index=2|pts=0|nb_samples=960\n",
    )
    first = programs(ctx)
    assert programs(ctx) == first
    assert first[0]["duration_seconds"] == 0.02
    assert closed == [True]


@pytest.mark.parametrize(
    "field,value", [("time_base", None), ("time_base", "0/0"), ("sample_rate_hz", 0)]
)
def test_invalid_clock_metadata_is_structured(
    tmp_path: Path, field: str, value: object
) -> None:
    ctx, closed = context(tmp_path, b"")
    ctx.streams[0][field] = value
    with pytest.raises(AppError, match="Invalid program clock metadata"):
        programs(ctx)
    assert not closed
