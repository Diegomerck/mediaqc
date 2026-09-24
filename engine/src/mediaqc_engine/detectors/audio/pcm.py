"""Run-local bounded PCM reuse; cache failure never replaces decode failure."""

from collections.abc import Generator
from contextlib import closing
from pathlib import Path
from typing import BinaryIO

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.detectors.contract import DetectorContext

# Disk budget across run caches in one project, not a measurement threshold.
MAX_CACHE_BYTES = 1024 * 1024 * 1024


def cleanup(directory: Path) -> None:
    for path in directory.glob("pcm-*.f64*"):
        try:
            if path.resolve().is_relative_to(directory.resolve()):
                path.unlink()
        except OSError:
            pass  # A cache permission failure must not mask the run outcome.


def recover(directory: Path) -> None:
    for child in directory.iterdir() if directory.is_dir() else ():
        if child.is_dir() and child.resolve().is_relative_to(directory.resolve()):
            cleanup(child)


def chunks(
    context: DetectorContext,
    stream: dict[str, object],
    arguments: list[str],
    block_bytes: int,
) -> Generator[bytes, None, None]:
    directory = Path(context.work_dir)
    path = directory / f"pcm-{stream['stream_index']}.f64"
    partial = path.with_suffix(".f64.partial")
    output: BinaryIO | None = None
    available = 0
    try:
        context.cancellation.check()
        if path.is_file():
            try:
                with path.open("rb") as source:
                    while data := source.read(block_bytes):
                        context.cancellation.check()
                        yield data
            except OSError as exc:
                raise AppError(
                    "PCM_CACHE_READ_FAILED",
                    "Cannot read temporary PCM measurements; retry the analysis",
                ) from exc
            return
        directory.mkdir(parents=True, exist_ok=True)
        available = MAX_CACHE_BYTES - sum(
            item.stat().st_size for item in directory.parent.glob("*/pcm-*.f64*")
        )
        duration = float(
            str(
                stream.get("duration_seconds")
                or context.media_asset.get("duration_seconds")
                or 0
            )
        )
        estimated = (
            duration
            * int(str(stream["sample_rate_hz"]))
            * int(str(stream["channel_count"]))
            * 8
        )
        if available > 0 and estimated <= available:
            output = partial.open("wb")
    except OSError:
        output = None
    try:
        with closing(context.media_tools.stream(arguments, block_bytes)) as decoded:
            for data in decoded:
                context.cancellation.check()
                if output is not None:
                    try:
                        if len(data) > available:
                            raise OSError("PCM cache budget exhausted")
                        output.write(data)
                        available -= len(data)
                    except OSError:
                        try:
                            output.close()
                        except OSError:
                            pass
                        output = None
                        try:
                            partial.unlink(missing_ok=True)
                        except OSError:
                            pass
                yield data
        context.cancellation.check()
        if output is not None:
            try:
                output.close()
                if partial.stat().st_size:
                    partial.replace(path)
            except OSError:
                pass
            output = None
    finally:
        if output is not None:
            try:
                output.close()
            except OSError:
                pass
        try:
            partial.unlink(missing_ok=True)
        except OSError:
            pass
