"""Phase 2 projects, canonical migration, probing and immutable-source fixtures."""

import hashlib
import io
import json
import sqlite3
import subprocess
import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.app.projects import Projects
from mediaqc_engine.db.project import SCHEMA, Project, absolute
from mediaqc_engine.ipc.server import handle_line, incoming
from mediaqc_engine.media.inspection import fingerprint, map_probe
from mediaqc_engine.media.tools import MediaTools


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    path = tmp_path / "音楽 O'Brien & Sons sample.wav"
    with wave.open(str(path), "wb") as output:
        output.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
        output.writeframes(b"\0" * (48000 * 4))
    return path


def test_canonical_schema_and_pragmas(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    specification = (root / "specs/03_DATABASE.md").read_text(encoding="utf-8")
    assert SCHEMA.read_text(encoding="utf-8").strip() in specification
    project = Project.create(tmp_path / "project", "Project")
    try:
        for pragma, value in (
            ("foreign_keys", 1),
            ("journal_mode", "wal"),
            ("synchronous", 1),
        ):
            assert project.connection.execute(f"PRAGMA {pragma}").fetchone()[0] == value
        assert (
            project.connection.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()[0]
            == "1"
        )
        with pytest.raises(sqlite3.IntegrityError):
            project.connection.execute(
                "INSERT INTO media_streams "
                "(id,media_asset_id,stream_index,stream_type) "
                "VALUES ('x','missing',0,'audio')"
            )
    finally:
        project.close()


def test_create_refuses_existing_content_and_invalid_open_keeps_project(
    tmp_path: Path,
) -> None:
    services = Projects()
    try:
        first = services.dispatch(
            "project.create", {"directory": str(tmp_path / "project"), "name": "Test"}
        )
        with pytest.raises(AppError, match="new or empty"):
            services.dispatch(
                "project.create",
                {"directory": str(tmp_path / "project"), "name": "Overwrite"},
            )
        with pytest.raises(AppError) as error:
            services.dispatch(
                "project.open",
                {"project_file": str(tmp_path / "missing/project.sqlite")},
            )
        assert error.value.code == "PROJECT_NOT_FOUND"
        assert services.dispatch("project.get", {})["id"] == first["id"]
    finally:
        services.close()


def test_reopen_and_inspect_wav_preserves_source(tmp_path: Path, audio: Path) -> None:
    before = hashlib.sha256(audio.read_bytes()).hexdigest(), audio.stat().st_mtime_ns
    services = Projects()
    project = services.dispatch(
        "project.create",
        {"directory": str(tmp_path / "Project 音楽 & space"), "name": "Episode"},
    )
    result = services.dispatch(
        "media.inspect", {"project_id": project["id"], "absolute_path": str(audio)}
    )
    assert set(result) == {"media_asset_id", "inspection_status", "metadata", "streams"}
    assert result["inspection_status"] == "COMPLETED"
    streams = result["streams"]
    assert isinstance(streams, list)
    assert streams[0]["sample_rate_hz"] == 48000
    assert streams[0]["channel_count"] == 2
    assert streams[0]["codec_name"] == "pcm_s16le"
    metadata = result["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["duration_seconds"] == pytest.approx(1.0, abs=0.01)
    services.close()
    reopened = services.dispatch(
        "project.open", {"project_file": project["project_file"]}
    )
    assert reopened["id"] == project["id"]
    assets = reopened["media_assets"]
    assert isinstance(assets, list) and len(assets) == 1
    services.close()
    assert (
        hashlib.sha256(audio.read_bytes()).hexdigest(),
        audio.stat().st_mtime_ns,
    ) == before
    assert list(audio.parent.glob(audio.name + ".*")) == []


def test_video_metadata(tmp_path: Path) -> None:
    path = tmp_path / "video & sample.mkv"
    tool = MediaTools().directory / "ffmpeg.exe"
    subprocess.run(
        [
            str(tool),
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=size=160x90:rate=25:duration=0.4",
            "-c:v",
            "ffv1",
            str(path),
        ],
        check=True,
        timeout=10,
        capture_output=True,
    )
    before = hashlib.sha256(path.read_bytes()).digest()
    metadata, streams = map_probe(MediaTools().probe(path))
    assert metadata["duration_seconds"] == pytest.approx(0.4, abs=0.04)
    assert streams[0]["width"] == 160 and streams[0]["height"] == 90
    assert streams[0]["avg_frame_rate"] == "25/1"
    assert hashlib.sha256(path.read_bytes()).digest() == before


@pytest.mark.parametrize("content", [b"not media", b"RIFF\xff\xff\xff\xffWAVEfmt "])
def test_invalid_and_corrupt_media_preserve_project_and_diagnostics(
    tmp_path: Path, content: bytes
) -> None:
    path = tmp_path / "invalid.wav"
    path.write_bytes(content)
    services = Projects()
    try:
        project = services.dispatch(
            "project.create",
            {"directory": str(tmp_path / "project"), "name": "Bad media"},
        )
        with pytest.raises(AppError) as error:
            services.dispatch(
                "media.inspect",
                {"project_id": project["id"], "absolute_path": str(path)},
            )
        assert error.value.code == "MEDIA_INSPECTION_FAILED"
        assert error.value.details["stderr_excerpt"]
        assets = services.dispatch("project.get", {})["media_assets"]
        assert isinstance(assets, list)
        assert assets[0]["inspection_status"] == "FAILED"
        assert path.read_bytes() == content
    finally:
        services.close()


def test_missing_source_and_changes(tmp_path: Path, audio: Path) -> None:
    services = Projects()
    try:
        project = services.dispatch(
            "project.create", {"directory": str(tmp_path / "project"), "name": "Files"}
        )
        with pytest.raises(AppError) as error:
            services.dispatch(
                "media.inspect",
                {
                    "project_id": project["id"],
                    "absolute_path": str(tmp_path / "missing.wav"),
                },
            )
        assert error.value.code == "MEDIA_NOT_FOUND"
        original = services.tools.probe

        def changed(path: Path) -> dict[str, object]:
            result = original(path)
            path.write_bytes(path.read_bytes() + b"test change")
            return result

        with patch.object(services.tools, "probe", side_effect=changed):
            with pytest.raises(AppError) as error:
                services.dispatch(
                    "media.inspect",
                    {"project_id": project["id"], "absolute_path": str(audio)},
                )
        assert error.value.code == "MEDIA_CHANGED"
    finally:
        services.close()


def test_invalid_project_is_not_modified(tmp_path: Path) -> None:
    project = Project.create(tmp_path / "project", "Version")
    path = project.path
    project.connection.execute("UPDATE schema_meta SET value='99'")
    project.connection.commit()
    project.close()
    before = path.read_bytes()
    with pytest.raises(AppError) as failure:
        Project.open(path)
    assert failure.value.code == "PROJECT_INVALID"
    assert path.read_bytes() == before


def test_failed_initial_migration_rolls_back(tmp_path: Path) -> None:
    with patch("mediaqc_engine.db.project.SCHEMA") as schema:
        schema.read_text.return_value = (
            "CREATE TABLE schema_meta(key TEXT); INVALID SQL;"
        )
        with pytest.raises(sqlite3.Error):
            Project.create(tmp_path / "project", "Migration")
    assert not (tmp_path / "project/project.sqlite").exists()


def test_tool_missing_failure_and_timeout(tmp_path: Path, audio: Path) -> None:
    tools = MediaTools(tmp_path, timeout=0)
    with pytest.raises(AppError):
        tools.probe(audio)
    (tmp_path / "ffprobe.exe").touch()
    child = MagicMock()
    child.poll.return_value = None
    child.__enter__.return_value = child
    with patch("mediaqc_engine.media.tools.subprocess.Popen", return_value=child):
        with pytest.raises(AppError, match="resource limit"):
            tools.probe(audio)
    child.kill.assert_called_once()
    child.wait.assert_called_once()
    assert tools.capability("ffmpeg") == {"available": False, "version": None}


@pytest.mark.parametrize("raw", [b"not JSON", b"[]", b'{"streams":[]}'])
def test_malformed_or_unsupported_probe_metadata(raw: bytes, audio: Path) -> None:
    tools = MediaTools()
    with patch.object(tools, "run", return_value=raw):
        with pytest.raises(AppError):
            map_probe(tools.probe(audio))


def test_shutdown_cancels_active_probe() -> None:
    services = Projects()
    services.tools.active.set()
    request = {
        "type": "request",
        "protocol_version": "1.0",
        "request_id": str(uuid4()),
        "method": "system.shutdown",
        "params": {},
    }
    assert (
        len(list(incoming(io.BytesIO(json.dumps(request).encode() + b"\n"), services)))
        == 1
    )
    assert services.tools.cancelled.is_set()


def test_phase2_invalid_params_preserve_protocol_session() -> None:
    services = Projects()
    request = {
        "type": "request",
        "protocol_version": "1.0",
        "request_id": str(uuid4()),
        "method": "project.create",
        "params": {"unexpected": True},
    }
    response, stopping = handle_line(json.dumps(request).encode(), services)
    assert response is not None and response["ok"] is False
    error = response["error"]
    assert isinstance(error, dict) and error["code"] == "INVALID_REQUEST"
    assert response["request_id"] == request["request_id"] and not stopping


@pytest.mark.parametrize(
    "value",
    ["relative.wav", "https://example.com/a.mp4", "", "\\\\server\\media.wav", 42],
)
def test_only_absolute_local_paths(value: object) -> None:
    with pytest.raises(AppError):
        absolute(value)


def test_fingerprint_is_bounded(tmp_path: Path) -> None:
    path = tmp_path / "sparse.bin"
    with path.open("wb") as output:
        output.truncate(128 * 1024 * 1024)
    first = fingerprint(path)
    assert first["file_size_bytes"] == 128 * 1024 * 1024
    assert len(str(first["fast_fingerprint_sha256"])) == 64


def test_new_engine_process_reopens_project_and_handles_errors(
    tmp_path: Path, audio: Path
) -> None:
    project = Project.create(tmp_path / "project", "IPC")
    identifier, path = project.id, project.path
    project.close()
    calls = [
        ("project.open", {"project_file": str(path)}),
        ("media.inspect", {"project_id": identifier, "absolute_path": str(audio)}),
        (
            "media.inspect",
            {"project_id": identifier, "absolute_path": str(tmp_path / "missing")},
        ),
        ("system.ping", {}),
        ("project.get", {}),
        ("system.shutdown", {}),
    ]
    messages = [
        {
            "type": "request",
            "protocol_version": "1.0",
            "request_id": str(uuid4()),
            "method": method,
            "params": params,
        }
        for method, params in calls
    ]
    result = subprocess.run(
        [sys.executable, "-m", "mediaqc_engine"],
        input="".join(json.dumps(item) + "\n" for item in messages).encode(),
        capture_output=True,
        timeout=20,
        check=True,
    )
    responses = [json.loads(item) for item in result.stdout.splitlines()][1:]
    assert len(responses) == len(messages)
    assert [item["request_id"] for item in responses] == [
        item["request_id"] for item in messages
    ]
    assert responses[1]["result"]["inspection_status"] == "COMPLETED"
    assert responses[2]["error"]["code"] == "MEDIA_NOT_FOUND"
    assert responses[3]["result"] == {"pong": True}
    assert len(responses[4]["result"]["media_assets"]) == 1
