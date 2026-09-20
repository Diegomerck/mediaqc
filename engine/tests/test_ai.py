"""Phase 8 contracts with deterministic embedded adapters; no model downloads."""

import hashlib
import json
import multiprocessing
import socket
import sqlite3
import threading
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import pytest
from ai_test_adapter import FakeProvider
from generate_test_media.audio import generate as audio
from generate_test_media.video import generate as video

from mediaqc_engine import ai, evidence
from mediaqc_engine.app.errors import AppError
from mediaqc_engine.app.projects import Projects
from mediaqc_engine.db import findings, runs
from mediaqc_engine.db.project import AI_SCHEMA, Project
from mediaqc_engine.detectors.common import StreamDetector
from mediaqc_engine.detectors.contract import DetectorContext, DetectorResult
from mediaqc_engine.jobs.cancellation import CancellationToken, Cancelled
from mediaqc_engine.media.tools import MediaTools
from mediaqc_engine.qc import profiles


@pytest.fixture
def provider(tmp_path: Path) -> FakeProvider:
    path = tmp_path / "test-model.bin"
    path.write_bytes(b"deterministic test fixture, not a production model")
    return FakeProvider(path)


@pytest.mark.parametrize("mode", ["ok", "incompatible", "capability_error", "missing"])
def test_local_availability(provider: FakeProvider, mode: str) -> None:
    provider.mode = mode
    if mode == "missing":
        provider.model.path.unlink()
    result = ai.capability(provider)
    assert result["local_available"] is (mode == "ok")
    assert not ai.capability(None)["local_available"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("confidence", float("nan")),
        ("confidence", float("inf")),
        ("confidence", True),
        ("confidence", -0.1),
        ("confidence", 1.1),
        ("recommended_action", "PASS"),
        ("finding_id", "another"),
        ("schema_version", "2"),
        ("model_id", "cloud"),
        ("model_version", "other"),
        ("summary", ""),
        ("summary", "x" * 2001),
        ("classification", ""),
        ("evidence_refs", ["foreign-evidence"]),
        ("severity", "INFO"),
    ],
)
def test_strict_schema(provider: FakeProvider, field: str, value: object) -> None:
    context: dict[str, object] = {"finding_id": "finding", "images": []}
    output = cast(dict[str, object], provider.review(context, 512))
    output[field] = value
    with pytest.raises(ValueError):
        ai.validate(output, context, provider.model)


@pytest.mark.parametrize(
    "mode",
    [
        "ok",
        "mutate",
        "fail",
        "malformed",
        "oversized",
        "missing",
        "timeout",
        "network_attempt",
    ],
)
def test_review_persistence_and_immutable_evidence(
    saved: tuple[Projects, str, str, Path],
    provider: FakeProvider,
    mode: str,
) -> None:
    service, run, identifier, _ = saved
    generate(saved)
    assert service.project is not None
    db, root = service.project.connection, service.project.path.parent
    with db:
        db.execute("UPDATE analysis_runs SET ai_mode='LOCAL' WHERE id=?", (run,))
    before = [tuple(row) for row in db.execute("SELECT * FROM findings")]
    evidence_before = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "evidence").rglob("*")
        if p.is_file()
    }
    finding = db.execute("SELECT * FROM findings WHERE id=?", (identifier,)).fetchone()
    context = ai.grounded_input(db, root, finding)
    assert set(context) == {
        "prompt_version",
        "instruction",
        "finding_id",
        "detector_id",
        "detector_version",
        "start_time_seconds",
        "end_time_seconds",
        "measurements",
        "thresholds",
        "images",
    }
    assert len(cast(list[object], context["images"])) <= 3
    assert str(root) not in json.dumps(context)
    assert "absolute_path" not in json.dumps(context)
    provider.mode = mode
    if mode == "missing":
        provider.model.path.unlink()
    with patch.object(ai, "REVIEW_SECONDS", 0.1 if mode == "timeout" else 5.0):
        ai.review_run(db, root, run, provider, CancellationToken())
    review = cast(
        dict[str, object],
        service.dispatch("finding.get", {"finding_id": identifier})["ai_review"],
    )
    assert review["status"] == (
        "COMPLETED" if mode in {"ok", "mutate"} else "UNAVAILABLE"
    )
    assert before == [tuple(row) for row in db.execute("SELECT * FROM findings")]
    assert evidence_before == {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "evidence").rglob("*")
        if p.is_file()
    }
    reopened = Project.open(service.project.path)
    try:
        assert (
            reopened.connection.execute("SELECT status FROM ai_reviews").fetchone()[0]
            == review["status"]
        )
    finally:
        reopened.close()


def test_off_skips_provider_and_persistence(
    saved: tuple[Projects, str, str, Path],
) -> None:
    service, run, _, _ = saved
    assert service.project is not None
    with patch.object(ai, "capability", side_effect=AssertionError("OFF invoked AI")):
        ai.review_run(
            service.project.connection,
            service.project.path.parent,
            run,
            None,
            CancellationToken(),
        )
    assert (
        service.project.connection.execute(
            "SELECT count(*) FROM ai_reviews"
        ).fetchone()[0]
        == 0
    )


@pytest.mark.parametrize("cancel", [False, True])
def test_timeout_and_cancellation_reap_worker(
    provider: FakeProvider, cancel: bool
) -> None:
    provider.mode = "timeout"
    token = CancellationToken()
    before = {child.pid for child in multiprocessing.active_children()}
    timer = threading.Timer(0.2, token.cancel)
    if cancel:
        timer.start()
    try:
        with pytest.raises(Cancelled if cancel else TimeoutError):
            ai.invoke(provider, {"finding_id": "f", "images": []}, 1, token)
    finally:
        timer.cancel()
    assert {child.pid for child in multiprocessing.active_children()} == before


class ResultDetector(StreamDetector):
    def __init__(self, severity: str):
        super().__init__("audio.clipping")
        self.severity = severity

    def analyze(self, context: DetectorContext) -> DetectorResult:
        item = self.finding(
            context, context.streams[0], {"measured": 42}, "Fixture", 0, 0.1
        )
        item["severity"] = self.severity
        return DetectorResult(metrics={"measured": 42}, findings=[item])


@pytest.mark.parametrize(
    "severity,expected", [("INFO", "PASS"), ("WARN", "WARN"), ("FAIL", "FAIL")]
)
@pytest.mark.parametrize("mode", ["OFF", "LOCAL"])
def test_deterministic_results_survive_ai_failure(
    session: tuple[Projects, str, Path, list[tuple[str, dict[str, object]]]],
    provider: FakeProvider,
    severity: str,
    expected: str,
    mode: str,
) -> None:
    service, asset, _, events = session
    service.jobs.detectors = (ResultDetector(severity),)
    provider.mode = "fail"
    service.jobs.ai_provider = provider
    result = finished(service, start(service, asset, ai_mode=mode))
    assert result["status"] == "COMPLETED"
    assert result["overall_result"] == expected
    finding = cast(list[dict[str, object]], result["findings"])[0]
    assert finding["measurements"] == {"measured": 42}
    assert finding["severity"] == severity and finding["disposition"] == "OPEN"
    if mode == "LOCAL":
        assert cast(dict[str, object], finding["ai_review"])["status"] == "UNAVAILABLE"
    else:
        assert "ai_review" not in finding
    assert not any(name == "analysis.failed" for name, _ in events)


def test_no_network_default_and_evidence_only_review(
    saved: tuple[Projects, str, str, Path],
    provider: FakeProvider,
) -> None:
    service, run, _, _ = saved
    assert service.project is not None
    db = service.project.connection
    with db:
        db.execute("UPDATE analysis_runs SET ai_mode='LOCAL' WHERE id=?", (run,))
    with patch.object(
        socket, "socket", side_effect=AssertionError("network forbidden")
    ):
        assert ai.capability(None)["local_available"] is False
        ai.review_run(
            db, service.project.path.parent, run, provider, CancellationToken()
        )
    assert db.execute("SELECT status FROM ai_reviews").fetchone()[0] == "COMPLETED"


def test_migration_backup_and_rollback(tmp_path: Path) -> None:
    project = Project.create(tmp_path / "project", "Migration")
    path = project.path
    with project.connection:
        project.connection.execute("DROP TABLE ai_reviews")
        project.connection.execute("UPDATE schema_meta SET value='1'")
    project.close()
    with patch.object(
        Path,
        "read_text",
        autospec=True,
        side_effect=lambda p, **kw: (
            "INVALID SQL" if p == AI_SCHEMA else original_read(p, **kw)
        ),
    ):
        with pytest.raises(AppError):
            Project.open(path)
    db = sqlite3.connect(path)
    assert db.execute("SELECT value FROM schema_meta").fetchone()[0] == "1"
    db.close()
    project = Project.open(path)
    assert (
        project.connection.execute("SELECT value FROM schema_meta").fetchone()[0] == "2"
    )
    project.close()
    backup = sqlite3.connect(path.with_name("project.schema-v1.sqlite.bak"))
    assert backup.execute("SELECT value FROM schema_meta").fetchone()[0] == "1"
    backup.close()


original_read = Path.read_text


@pytest.mark.parametrize("failure", ["missing_evidence", "budget", "persistence"])
def test_optional_failures_preserve_completed_result(
    saved: tuple[Projects, str, str, Path],
    provider: FakeProvider,
    failure: str,
) -> None:
    service, run, identifier, _ = saved
    references = generate(saved)
    assert service.project is not None
    db, root = service.project.connection, service.project.path.parent
    with db:
        db.execute("UPDATE analysis_runs SET ai_mode='LOCAL' WHERE id=?", (run,))
    runs.transition(db, run, "COMPLETED")
    before = tuple(
        db.execute("SELECT * FROM analysis_runs WHERE id=?", (run,)).fetchone()
    )
    if failure == "missing_evidence":
        image = next(item for item in references if item["mime_type"] == "image/png")
        (root / str(image["relative_path"])).unlink()
    if failure == "persistence":
        db.execute(
            "CREATE TRIGGER deny_ai BEFORE INSERT ON ai_reviews "
            "BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
    with patch.object(ai, "RUN_SECONDS", 0.0 if failure == "budget" else 120.0):
        ai.review_run(db, root, run, provider, CancellationToken())
    assert (
        tuple(db.execute("SELECT * FROM analysis_runs WHERE id=?", (run,)).fetchone())
        == before
    )
    if failure != "persistence":
        assert (
            db.execute(
                "SELECT status FROM ai_reviews WHERE finding_id=?", (identifier,)
            ).fetchone()[0]
            == "UNAVAILABLE"
        )


def test_input_limit_and_review_limit(
    saved: tuple[Projects, str, str, Path],
    provider: FakeProvider,
) -> None:
    with pytest.raises(ValueError, match="AI_INPUT_LIMIT"):
        ai.invoke(provider, {"oversized": "x" * ai.MAX_INPUT}, 1, CancellationToken())
    service, run, _, _ = saved
    assert service.project is not None
    db = service.project.connection
    with db:
        db.execute("UPDATE analysis_runs SET ai_mode='LOCAL' WHERE id=?", (run,))
    with (
        patch.object(ai, "MAX_REVIEWS", 0),
        patch.object(ai, "invoke", return_value=True) as invoke,
    ):
        ai.review_run(
            db, service.project.path.parent, run, provider, CancellationToken()
        )
    assert invoke.call_count == 1  # compatibility only; zero review calls
    assert db.execute("SELECT count(*) FROM ai_reviews").fetchone()[0] == 0


def test_unavailable_model_and_retry_do_not_block_qc(
    session: tuple[Projects, str, Path, list[tuple[str, dict[str, object]]]],
) -> None:
    service, asset, _, _ = session
    service.jobs.detectors = (ResultDetector("WARN"),)
    result = finished(service, start(service, asset, ai_mode="LOCAL"))
    assert result["status"] == "COMPLETED" and result["overall_result"] == "WARN"
    retry = service.dispatch("analysis.retry", {"analysis_run_id": result["id"]})
    next_run = finished(service, str(retry["analysis_run_id"]))
    assert next_run["ai_mode"] == "LOCAL"
    assert next_run["status"] == "COMPLETED" and next_run["overall_result"] == "WARN"


@pytest.fixture(params=["audio", "video"])
def saved(
    request: pytest.FixtureRequest, tmp_path: Path
) -> Iterator[tuple[Projects, str, str, Path]]:
    kind = str(request.param)
    directory = tmp_path / "source 音楽 O'Brien & Sons"
    source = (
        audio("audio.clipping.001", directory)
        if kind == "audio"
        else video("video.black.001", directory)
    )
    before = hashlib.sha256(source.read_bytes()).digest(), source.stat().st_mtime_ns
    siblings = sorted(directory.iterdir())
    service = Projects(state_directory=tmp_path / "state")
    project = service.dispatch(
        "project.create", {"directory": str(tmp_path / "project é"), "name": "Evidence"}
    )
    inspected = service.dispatch(
        "media.inspect", {"project_id": project["id"], "absolute_path": str(source)}
    )
    assert service.project is not None
    db = service.project.connection
    asset = db.execute(
        "SELECT * FROM media_assets WHERE id=?", (inspected["media_asset_id"],)
    ).fetchone()
    stream = db.execute(
        "SELECT * FROM media_streams WHERE media_asset_id=?", (asset["id"],)
    ).fetchone()
    run = runs.create(
        db,
        service.project.id,
        asset["id"],
        profiles.builtin(),
        asset["fast_fingerprint_sha256"],
    )
    identifier, execution = str(uuid4()), str(uuid4())
    detector = "audio.clipping" if kind == "audio" else "video.black_frame"
    with db:
        db.execute(
            "INSERT INTO detector_executions "
            "(id,analysis_run_id,detector_id,detector_version,status) "
            "VALUES (?,?,?,?,?)",
            (execution, run, detector, "1.0.0", "COMPLETED"),
        )
        findings.save(
            db,
            service.project.path.parent,
            run,
            execution,
            {
                "id": identifier,
                "detector_id": detector,
                "detector_version": "1.0.0",
                "stream_id": stream["id"],
                "severity": "FAIL",
                "confidence": None,
                "start_time_seconds": 2.0,
                "end_time_seconds": 2.2,
                "duration_seconds": 0.2,
                "title": "Fixture",
                "description": "Known injected issue",
                "disposition": "OPEN",
                "measurements": {"measured": 1},
                "threshold": {"limit": 0},
                "metadata": {},
            },
        )
    runs.transition(db, run, "INSPECTING")
    runs.transition(db, run, "ANALYZING")
    try:
        yield service, run, identifier, source
    finally:
        service.close()
        assert before == (
            hashlib.sha256(source.read_bytes()).digest(),
            source.stat().st_mtime_ns,
        )
        assert siblings == sorted(directory.iterdir())


def generate(saved: tuple[Projects, str, str, Path]) -> list[dict[str, object]]:
    service, run, identifier, _ = saved
    assert service.project is not None
    token = CancellationToken()
    tools = MediaTools(
        cancellation=token.event, cache=service.project.path.parent / "cache"
    )
    evidence.generate(
        service.project.connection, service.project.path.parent, run, tools, token
    )
    assert tools.pids == []
    detail = service.dispatch("finding.get", {"finding_id": identifier})
    assert cast(dict[str, object], detail["metadata"])["visual_evidence_errors"] == []
    return cast(list[dict[str, object]], detail["evidence"])


@pytest.fixture
def session(
    tmp_path: Path,
) -> Iterator[tuple[Projects, str, Path, list[tuple[str, dict[str, object]]]]]:
    source = tmp_path / "音楽 O'Brien & Sons source.wav"
    with wave.open(str(source), "wb") as output:
        output.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        output.writeframes(b"\0" * 96000)
    events: list[tuple[str, dict[str, object]]] = []
    services = Projects(
        emit=lambda name, data: events.append((name, data)),
        state_directory=tmp_path / "journal",
    )
    project = services.dispatch(
        "project.create", {"name": "Jobs", "directory": str(tmp_path / "project")}
    )
    asset = services.dispatch(
        "media.inspect", {"project_id": project["id"], "absolute_path": str(source)}
    )
    before = hashlib.sha256(source.read_bytes()).digest(), source.stat().st_mtime_ns
    try:
        yield services, str(asset["media_asset_id"]), source, events
    finally:
        services.close()
        assert (
            hashlib.sha256(source.read_bytes()).digest(),
            source.stat().st_mtime_ns,
        ) == before


def start(services: Projects, asset: str, **overrides: object) -> str:
    assert services.project is not None
    result = services.dispatch(
        "analysis.start",
        {
            "project_id": services.project.id,
            "media_asset_id": asset,
            "profile_key": "general_technical_qc",
            "profile_version": "1.1.0",
            "ai_mode": "OFF",
            **overrides,
        },
    )
    assert result["status"] == "QUEUED"
    return str(result["analysis_run_id"])


def finished(services: Projects, identifier: str) -> dict[str, object]:
    assert services.jobs.worker is not None
    services.jobs.worker.join(8)
    assert not services.jobs.active
    return services.dispatch("analysis.get", {"analysis_run_id": identifier})
