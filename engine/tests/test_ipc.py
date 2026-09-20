"""Phase 1 framing, dispatch, correlation and process lifecycle regressions."""

import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from mediaqc_engine.ipc.server import MAX_LINE_BYTES, handle_line, serve


def request(method: str = "system.ping", **changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "type": "request",
        "protocol_version": "1.0",
        "request_id": str(uuid4()),
        "method": method,
        "params": {},
    }
    value.update(changes)
    return value


def line(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8") + b"\n"


def test_exact_ready_ping_and_shutdown() -> None:
    ping, shutdown, ignored = request(), request("system.shutdown"), request()
    output = io.BytesIO()
    serve(io.BytesIO(line(ping) + line(shutdown) + line(ignored)), output)
    assert b"\r\n" not in output.getvalue()
    assert output.getvalue().endswith(b"\n")
    assert [json.loads(item) for item in output.getvalue().splitlines()] == [
        {
            "type": "event",
            "protocol_version": "1.0",
            "event": "engine.ready",
            "data": {},
        },
        {
            "type": "response",
            "protocol_version": "1.0",
            "request_id": ping["request_id"],
            "ok": True,
            "result": {"pong": True},
        },
        {
            "type": "response",
            "protocol_version": "1.0",
            "request_id": shutdown["request_id"],
            "ok": True,
            "result": {},
        },
    ]


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"method": "report.generate"}, "PROJECT_NOT_FOUND"),
        ({"method": "system.version"}, "METHOD_NOT_FOUND"),
        ({"protocol_version": "2.0"}, "PROTOCOL_VERSION_UNSUPPORTED"),
        ({"type": "event"}, "INVALID_REQUEST"),
        ({"params": []}, "INVALID_REQUEST"),
        ({"params": {"path": "C:/音楽/O'Brien & Sons/file.mov"}}, "INVALID_REQUEST"),
        ({"method": 42}, "INVALID_REQUEST"),
        ({"extra": True}, "INVALID_REQUEST"),
        ({"request_id": "invalid"}, "INVALID_REQUEST"),
    ],
)
def test_correlated_errors(changes: dict[str, object], code: str) -> None:
    value = request()
    value.update(changes)
    response, shutdown = handle_line(line(value))
    assert response is not None
    assert not shutdown
    assert set(response) == {"type", "protocol_version", "request_id", "ok", "error"}
    assert response["type"] == "response"
    assert response["protocol_version"] == "1.0"
    assert response["request_id"] == value["request_id"]
    assert response["ok"] is False
    detail = response["error"]
    assert isinstance(detail, dict)
    assert set(detail) == {"code", "message", "details"}
    assert detail["code"] == code
    assert detail["details"] == {}


@pytest.mark.parametrize(
    "malformed", [b"{", b"[]", b"null", b"{}", b"\xff", b'{"x":NaN}', b'{"x":1,"x":2}']
)
def test_uncorrelatable_input_does_not_fabricate_id(malformed: bytes) -> None:
    assert handle_line(malformed) == (None, False)


def test_capabilities_are_truthful_and_versioned() -> None:
    with patch(
        "mediaqc_engine.app.system.MediaTools.capability",
        return_value={"available": False, "version": None},
    ):
        response, _ = handle_line(line(request("system.capabilities")))
    assert response is not None
    assert response["result"] == {
        "engine_version": "0.0.0",
        "protocol_version": "1.0",
        "schema_version": 2,
        "platform": "windows" if sys.platform == "win32" else sys.platform,
        "ffmpeg": {"available": False, "version": None},
        "ffprobe": {"available": False, "version": None},
        "ai": {
            "local_available": False,
            "provider": None,
            "model_id": None,
            "model_version": None,
            "reason": "No embedded provider/model installed",
        },
        "detectors": [
            {
                "id": identifier,
                "version": "1.0.0",
                "media_types": [identifier.split(".")[0]],
                "requires_ai": False,
            }
            for identifier in (
                "audio.loudness.integrated",
                "audio.loudness.short_term",
                "audio.loudness.momentary",
                "audio.loudness.range",
                "audio.true_peak",
                "audio.sample_peak",
                "audio.clipping",
                "audio.silence",
                "audio.channel_imbalance",
                "audio.phase_correlation",
                "audio.hum",
                "audio.noise_floor",
                "audio.dropout",
                "audio.discontinuity",
                "video.decode_integrity",
                "video.frame_rate",
                "video.timestamp_integrity",
                "video.black_frame",
                "video.near_black_frame",
                "video.freeze",
                "video.duplicate_frame",
                "video.frame_cadence",
                "video.luminance_anomaly",
                "video.flash",
                "video.exposure_anomaly",
                "video.color_anomaly",
                "video.visual_anomaly",
            )
        ],
    }


def test_service_failure_is_structured() -> None:
    with patch("mediaqc_engine.ipc.server.capabilities", side_effect=RuntimeError):
        response, _ = handle_line(line(request("system.capabilities")))
    assert response is not None
    assert response["error"] == {
        "code": "ENGINE_INTERNAL_ERROR",
        "message": "System service failed",
        "details": {},
    }


def test_oversized_and_unterminated_lines() -> None:
    output = io.BytesIO()
    serve(
        io.BytesIO(b"x" * (MAX_LINE_BYTES + 20) + b"\n" + line(request()) + b"{}"),
        output,
    )
    messages = [json.loads(item) for item in output.getvalue().splitlines()]
    assert len(messages) == 2
    assert messages[1]["result"] == {"pong": True}


def test_10000_messages_and_stderr_isolation(tmp_path: Path) -> None:
    directory = tmp_path / "音楽 O'Brien & Sons"
    directory.mkdir()
    requests = [request() for _ in range(10000)]
    shutdown = request("system.shutdown")
    process = subprocess.run(
        [sys.executable, "-m", "mediaqc_engine"],
        input=b"invalid-json\n" + b"".join(map(line, requests)) + line(shutdown),
        capture_output=True,
        cwd=directory,
        timeout=30,
        check=True,
    )
    messages = [json.loads(item) for item in process.stdout.splitlines()]
    assert len(messages) == 10002
    assert len({item["request_id"] for item in messages[1:]}) == 10001
    for sent, received in zip(requests, messages[1:-1], strict=True):
        assert received["request_id"] == sent["request_id"]
        assert received["result"] == {"pong": True}
    assert b"INVALID_REQUEST" in process.stderr
    assert b"invalid-json" not in process.stderr
    assert b"\r\n" not in process.stdout


def test_stdin_eof_exits_cleanly() -> None:
    process = subprocess.run(
        [sys.executable, "-m", "mediaqc_engine"],
        input=b"",
        capture_output=True,
        timeout=10,
        check=True,
    )
    assert json.loads(process.stdout)["event"] == "engine.ready"
    assert process.stderr == b""


def test_invalid_surrogate_id_does_not_break_output_encoding() -> None:
    malformed = request(request_id="\ud800")
    output = io.BytesIO()
    serve(io.BytesIO(json.dumps(malformed).encode() + b"\n" + line(request())), output)
    messages = [json.loads(item) for item in output.getvalue().splitlines()]
    assert messages[1]["error"]["code"] == "INVALID_REQUEST"
    assert messages[2]["result"] == {"pong": True}
