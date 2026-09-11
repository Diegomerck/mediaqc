"""Strict protocol framing and dispatch, independent of the desktop UI."""

import json
import logging
import queue
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.app.projects import METHODS, Projects
from mediaqc_engine.app.system import PROTOCOL_VERSION, capabilities

LOG = logging.getLogger(__name__)
# Transport resource bound, not a QC policy threshold.
MAX_LINE_BYTES = 1024 * 1024


def error(request_id: str, code: str, message: str) -> dict[str, object]:
    return {
        "type": "response",
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "ok": False,
        "error": {"code": code, "message": message, "details": {}},
    }


def reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def handle_line(
    line: bytes, projects: Projects | None = None
) -> tuple[dict[str, object] | None, bool]:
    """Uncorrelatable input is logged, never assigned a fabricated request ID."""
    try:
        request = json.loads(
            line.decode("utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=unique_keys,
        )
    except (ValueError, RecursionError):
        LOG.warning("INVALID_REQUEST: malformed JSON or UTF-8 (content omitted)")
        return None, False
    if not isinstance(request, dict):
        LOG.warning("INVALID_REQUEST: expected object")
        return None, False
    request_id = request.get("request_id")
    if not isinstance(request_id, str):
        LOG.warning("INVALID_REQUEST: missing string request_id")
        return None, False
    try:
        UUID(request_id)
    except ValueError:
        return error(request_id, "INVALID_REQUEST", "request_id must be a UUID"), False
    if (
        set(request) != {"type", "protocol_version", "request_id", "method", "params"}
        or request["type"] != "request"
        or not isinstance(request["method"], str)
        or not isinstance(request["params"], dict)
        or not isinstance(request["protocol_version"], str)
    ):
        return error(request_id, "INVALID_REQUEST", "Invalid request envelope"), False
    if request["protocol_version"] != PROTOCOL_VERSION:
        return error(
            request_id, "PROTOCOL_VERSION_UNSUPPORTED", "Expected protocol version 1.0"
        ), False
    method = request["method"]
    if (
        method
        not in {"system.ping", "system.capabilities", "system.shutdown"} | METHODS
    ):
        return error(request_id, "METHOD_NOT_FOUND", "Method is not implemented"), False
    if method not in METHODS and request["params"]:
        return error(
            request_id, "INVALID_REQUEST", "System params must be empty"
        ), False
    try:
        if method in METHODS:
            if projects is None:
                raise AppError("PROJECT_NOT_FOUND", "No project session is available")
            result = projects.dispatch(method, request["params"])
        else:
            if method == "system.shutdown" and projects is not None:
                projects.jobs.shutdown()
            result = (
                capabilities()
                if method == "system.capabilities"
                else {"pong": True}
                if method == "system.ping"
                else {}
            )
    except AppError as failure:
        response = error(request_id, failure.code, failure.message)
        response["error"] = {
            "code": failure.code,
            "message": failure.message,
            "details": failure.details,
        }
        return response, False
    except Exception:
        # Do not include request content or media paths in diagnostics.
        LOG.error("ENGINE_INTERNAL_ERROR: system service failed")
        return error(
            request_id, "ENGINE_INTERNAL_ERROR", "System service failed"
        ), False
    return {
        "type": "response",
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "ok": True,
        "result": result,
    }, method == "system.shutdown"


def write_message(output: BinaryIO, message: dict[str, object]) -> None:
    output.write(
        json.dumps(
            message, ensure_ascii=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )
    output.flush()


def serve(
    source: BinaryIO, output: BinaryIO, state_directory: Path | None = None
) -> None:
    lock = threading.Lock()

    def send(message: dict[str, object]) -> None:
        with lock:
            write_message(output, message)

    def emit(event: str, data: dict[str, object]) -> None:
        try:
            send(
                {
                    "type": "event",
                    "protocol_version": PROTOCOL_VERSION,
                    "event": event,
                    "data": data,
                }
            )
        except OSError:
            LOG.warning("Desktop event pipe closed")

    projects = Projects(emit=emit, state_directory=state_directory)
    try:
        serve_session(source, output, projects, send)
    finally:
        projects.close()


def serve_session(
    source: BinaryIO,
    output: BinaryIO,
    projects: Projects,
    send: Callable[[dict[str, object]], None] | None = None,
) -> None:
    writer = (
        send if send is not None else lambda message: write_message(output, message)
    )
    writer(
        {
            "type": "event",
            "protocol_version": PROTOCOL_VERSION,
            "event": "engine.ready",
            "data": {},
        },
    )
    for line in incoming(source, projects):
        if not line.endswith(b"\n"):
            LOG.warning("INVALID_REQUEST: unterminated protocol line at EOF")
            return
        response, shutdown = handle_line(line, projects)
        if response is not None:
            writer(response)
        if shutdown:
            return


def incoming(source: BinaryIO, projects: Projects) -> Iterator[bytes]:
    """Read shutdown while a probe is active, without introducing analysis jobs."""
    lines: queue.Queue[bytes | None] = queue.Queue(maxsize=64)

    def reader() -> None:
        stopping = False
        try:
            while line := source.readline(MAX_LINE_BYTES + 1):
                if len(line) > MAX_LINE_BYTES:
                    LOG.warning(
                        "INVALID_REQUEST: protocol line exceeds transport limit"
                    )
                    while line and not line.endswith(b"\n"):
                        line = source.readline(MAX_LINE_BYTES + 1)
                    continue
                try:
                    value = json.loads(line)
                    if (
                        isinstance(value, dict)
                        and value.get("method") == "system.shutdown"
                    ):
                        _, stopping = handle_line(line)
                except (ValueError, RecursionError):
                    pass
                if stopping and projects.tools.active.is_set():
                    projects.tools.cancelled.set()
                lines.put(line)
                if stopping:
                    break
        finally:
            if not stopping and projects.tools.active.is_set():
                projects.tools.cancelled.set()
            lines.put(None)

    threading.Thread(target=reader, daemon=True).start()
    while (line := lines.get()) is not None:
        yield line
