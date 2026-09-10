"""Strict protocol framing and Phase 1 dispatch, independent of the desktop UI."""

import json
import logging
from typing import BinaryIO
from uuid import UUID

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


def handle_line(line: bytes) -> tuple[dict[str, object] | None, bool]:
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
    if method not in {"system.ping", "system.capabilities", "system.shutdown"}:
        return error(request_id, "METHOD_NOT_FOUND", "Method is not implemented"), False
    if request["params"]:
        return error(
            request_id, "INVALID_REQUEST", "System params must be empty"
        ), False
    try:
        result = (
            capabilities()
            if method == "system.capabilities"
            else {"pong": True}
            if method == "system.ping"
            else {}
        )
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


def serve(source: BinaryIO, output: BinaryIO) -> None:
    write_message(
        output,
        {
            "type": "event",
            "protocol_version": PROTOCOL_VERSION,
            "event": "engine.ready",
            "data": {},
        },
    )
    while line := source.readline(MAX_LINE_BYTES + 1):
        if len(line) > MAX_LINE_BYTES:
            LOG.warning("INVALID_REQUEST: protocol line exceeds transport limit")
            while not line.endswith(b"\n"):
                line = source.readline(MAX_LINE_BYTES + 1)
                if not line:
                    return
            continue
        if not line.endswith(b"\n"):
            LOG.warning("INVALID_REQUEST: unterminated protocol line at EOF")
            return
        response, shutdown = handle_line(line)
        if response is not None:
            write_message(output, response)
        if shutdown:
            return
