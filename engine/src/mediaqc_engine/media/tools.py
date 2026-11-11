"""Bundled media tool resolution and bounded subprocess ownership."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

from mediaqc_engine.app.errors import AppError


def tool_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "ffmpeg"
    return Path(__file__).resolve().parents[3] / "vendor/ffmpeg"


class MediaTools:
    def __init__(
        self,
        directory: Path | None = None,
        timeout: float = 30,
        cancellation: threading.Event | None = None,
        cache: Path | None = None,
    ):
        self.directory = directory if directory is not None else tool_directory()
        self.timeout = timeout
        self.cancelled = cancellation if cancellation is not None else threading.Event()
        self.active = threading.Event()
        self.cache = cache
        self._lock = threading.Lock()
        self._children: set[subprocess.Popen[bytes]] = set()

    @property
    def pids(self) -> list[int]:
        with self._lock:
            return [child.pid for child in self._children]

    def cancel(self) -> None:
        self.cancelled.set()
        with self._lock:
            for child in self._children:
                if child.poll() is None:
                    child.kill()
                child.wait()

    @contextmanager
    def own(self, child: subprocess.Popen[bytes]) -> Iterator[None]:
        with self._lock:
            self._children.add(child)
            if self.cancelled.is_set():
                child.kill()
        try:
            yield
        finally:
            with self._lock:
                if child.poll() is None:
                    child.kill()
                child.wait()
                self._children.discard(child)

    def run(self, tool: str, arguments: list[str]) -> bytes:
        ext = ".exe" if sys.platform == "win32" else ""
        executable = self.directory / f"{tool}{ext}"
        if not executable.is_file():
            raise AppError(
                "MEDIA_INSPECTION_FAILED",
                "Bundled media tools are missing; rebuild or reinstall MediaQC",
            )
        if sys.platform != "win32" and not os.access(executable, os.X_OK):
            try:
                os.chmod(executable, os.stat(executable).st_mode | 0o755)
            except OSError:
                pass
        # Temporary output is in the engine cache, never adjacent to source media.
        cache = self.cache or Path(tempfile.gettempdir()) / "MediaQC/cache"
        cache.mkdir(parents=True, exist_ok=True)
        # The child shares these file positions. Buffered seek/tell bookkeeping
        # can race with its writes on Windows, yielding truncated probe JSON.
        # Inspect file sizes without moving the writer's cursor.
        with (
            tempfile.TemporaryFile(dir=cache, buffering=0) as output,
            tempfile.TemporaryFile(dir=cache, buffering=0) as errors,
        ):
            try:
                with (
                    subprocess.Popen(
                        [str(executable), *arguments],
                        stdin=subprocess.DEVNULL,
                        stdout=output,
                        stderr=errors,
                        shell=False,
                        creationflags=subprocess.CREATE_NO_WINDOW
                        if sys.platform == "win32"
                        else 0,
                    ) as child,
                    self.own(child),
                ):
                    deadline = time.monotonic() + self.timeout
                    while child.poll() is None:
                        if (
                            self.cancelled.is_set()
                            or time.monotonic() >= deadline
                            or os.fstat(output.fileno()).st_size > 64 * 1024
                            or os.fstat(errors.fileno()).st_size > 64 * 1024
                        ):
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

    def stream(
        self,
        arguments: list[str],
        block_bytes: int = 65536,
        *,
        tool: str = "ffmpeg",
        reject_errors: bool = False,
    ) -> Generator[bytes, None, None]:
        """Bounded decode pipe; own() reaps on cancellation, error or early close."""
        from mediaqc_engine.jobs.cancellation import Cancelled

        if tool not in {"ffmpeg", "ffprobe"}:
            raise ValueError("Unsupported bundled tool")
        if self.cancelled.is_set():
            raise Cancelled()
        ext = ".exe" if sys.platform == "win32" else ""
        executable = self.directory / f"{tool}{ext}"
        if not executable.is_file():
            raise AppError(
                "MEDIA_UNSUPPORTED",
                "Bundled media tools are missing; rebuild or reinstall MediaQC",
            )
        if sys.platform != "win32" and not os.access(executable, os.X_OK):
            try:
                os.chmod(executable, os.stat(executable).st_mode | 0o755)
            except OSError:
                pass
        excerpt: deque[bytes] = deque(maxlen=8)
        try:
            with (
                subprocess.Popen(
                    [
                        str(executable),
                        *(["-nostdin"] if tool == "ffmpeg" else []),
                        "-v",
                        "error",
                        *arguments,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    creationflags=subprocess.CREATE_NO_WINDOW
                    if sys.platform == "win32"
                    else 0,
                ) as child,
                self.own(child),
            ):
                assert child.stdout is not None and child.stderr is not None
                stderr = child.stderr

                def drain() -> None:
                    while chunk := stderr.read(512):
                        excerpt.append(chunk)

                reader = threading.Thread(target=drain, daemon=True)
                reader.start()
                try:
                    while chunk := child.stdout.read(block_bytes):
                        if self.cancelled.is_set():
                            raise Cancelled()
                        yield chunk
                    child.wait()
                    if self.cancelled.is_set():
                        raise Cancelled()
                    reader.join()
                    if child.returncode or (reject_errors and excerpt):
                        raise AppError(
                            "MEDIA_UNSUPPORTED",
                            "Media decoding failed",
                            {
                                "exit_code": child.returncode,
                                "stderr_excerpt": b"".join(excerpt).decode(
                                    "utf-8", errors="replace"
                                ),
                            },
                        )
                finally:
                    if child.poll() is None:
                        child.kill()
                    child.wait()
                    reader.join()
        except OSError as exc:
            raise AppError(
                "MEDIA_UNSUPPORTED", "Cannot launch bundled media decoder"
            ) from exc

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
