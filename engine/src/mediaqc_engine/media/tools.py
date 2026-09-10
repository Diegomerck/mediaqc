"""Bundled media tool resolution and bounded subprocess ownership."""

import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from mediaqc_engine.app.errors import AppError


def tool_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "ffmpeg"
    return Path(__file__).resolve().parents[3] / "vendor/ffmpeg"


class MediaTools:
    def __init__(self, directory: Path | None = None, timeout: float = 30):
        self.directory = directory if directory is not None else tool_directory()
        self.timeout = timeout
        self.cancelled = threading.Event()
        self.active = threading.Event()

    def run(self, tool: str, arguments: list[str]) -> bytes:
        executable = self.directory / f"{tool}.exe"
        if not executable.is_file():
            raise AppError(
                "MEDIA_INSPECTION_FAILED",
                "Bundled media tools are missing; rebuild or reinstall MediaQC",
            )
        # Temporary output is in the engine cache, never adjacent to source media.
        cache = Path(tempfile.gettempdir()) / "MediaQC/cache"
        cache.mkdir(parents=True, exist_ok=True)
        with (
            tempfile.TemporaryFile(dir=cache) as output,
            tempfile.TemporaryFile(dir=cache) as errors,
        ):
            try:
                with subprocess.Popen(
                    [str(executable), *arguments],
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=errors,
                    shell=False,
                    creationflags=subprocess.CREATE_NO_WINDOW
                    if sys.platform == "win32"
                    else 0,
                ) as child:
                    deadline = time.monotonic() + self.timeout
                    while child.poll() is None:
                        if (
                            self.cancelled.is_set()
                            or time.monotonic() >= deadline
                            or output.tell() > 64 * 1024
                            or errors.tell() > 64 * 1024
                        ):
                            child.kill()
                            child.wait()
                            raise AppError(
                                "MEDIA_INSPECTION_FAILED",
                                "Inspection was interrupted or exceeded "
                                "its resource limit",
                            )
                        time.sleep(0.02)
                    errors.seek(0)
                    excerpt = errors.read(4096).decode("utf-8", errors="replace")
                    if child.returncode != 0:
                        raise AppError(
                            "MEDIA_INSPECTION_FAILED",
                            "The bundled media probe could not inspect this file",
                            {"exit_code": child.returncode, "stderr_excerpt": excerpt},
                        )
                    output.seek(0)
                    result = output.read(64 * 1024 + 1)
                    if len(result) > 64 * 1024:
                        raise AppError(
                            "MEDIA_INSPECTION_FAILED",
                            "Probe metadata exceeded the transport limit",
                        )
                    return result
            except OSError as exc:
                raise AppError(
                    "MEDIA_INSPECTION_FAILED",
                    "Could not execute the bundled media tool",
                ) from exc

    def capability(self, tool: str) -> dict[str, object]:
        try:
            text = (
                self.run(tool, ["-version"])
                .decode("utf-8", errors="replace")
                .splitlines()[0]
            )
            return {"available": True, "version": text}
        except (AppError, IndexError):
            return {"available": False, "version": None}

    def probe(self, path: Path) -> dict[str, object]:
        raw = self.run(
            "ffprobe",
            [
                "-v",
                "error",
                "-protocol_whitelist",
                "file",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                "-i",
                str(path),
            ],
        )
        try:
            value: object = json.loads(raw)
        except (ValueError, RecursionError) as exc:
            raise AppError(
                "MEDIA_INSPECTION_FAILED", "Probe returned malformed metadata"
            ) from exc
        if not isinstance(value, dict):
            raise AppError(
                "MEDIA_INSPECTION_FAILED", "Probe did not return a metadata object"
            )
        return value
