"""Phase 10 persistence, discovery, queue and recovery regressions."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import pytest

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.app.projects import Projects
from mediaqc_engine.db import batches, findings, runs
from mediaqc_engine.db.project import BATCH_SCHEMA, Project
from mediaqc_engine.detectors.contract import DetectorContext, DetectorResult
from mediaqc_engine.explanations import explain
from mediaqc_engine.media.tools import MediaTools
from mediaqc_engine.qc import profiles


@pytest.fixture
def batch_session(
    tmp_path: Path,
) -> Iterator[tuple[Projects, Path, ControlledDetector]]:
    source = tmp_path / "sources"
    source.mkdir()
    detector = ControlledDetector()
    detector.release.set()
    service = Projects()
    service.dispatch(
        "project.create",
        {"directory": str(tmp_path / "project"), "name": "Batch tests"},
    )
    service.jobs.detectors = (detector,)
    try:
        yield service, source, detector
    finally:
        detector.release.set()
        service.close()


def wav(path: Path) -> None:
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        output.writeframes(b"\0" * 960)


def import_batch(
    service: Projects, source: Path, folder: bool = True, recursive: bool = False
) -> str:
    assert service.project is not None
    response = service.dispatch(
        "batch.create",
        {
            "project_id": service.project.id,
            "name": "Imported",
            "source_kind": "FOLDER" if folder else "FILE",
            "absolute_path": str(source),
            "recursive": recursive,
        },
    )
    wait_batch(service)
    return str(response["batch_id"])


def start_batch(service: Projects, identifier: str) -> None:
    profile = profiles.builtin()
    service.dispatch(
        "batch.start",
        {
            "batch_id": identifier,
            "profile_key": profile["profile_key"],
            "profile_version": profile["version"],
            "ai_mode": "OFF",
        },
    )


def test_migration_003_wal_backup_and_rollback(tmp_path: Path) -> None:
    project = Project.create(tmp_path / "project", "Batch project")
    path = project.path
    with project.connection:
        for table in ("batch_reports", "batch_items", "batches"):
            project.connection.execute(f"DROP TABLE {table}")
        project.connection.execute("UPDATE schema_meta SET value='2'")
        project.connection.execute("UPDATE projects SET notes='Committed history'")
    project.close()
    read = Path.read_text
    with patch.object(
        Path,
        "read_text",
        autospec=True,
        side_effect=lambda p, **kw: (
            "INVALID SQL" if p == BATCH_SCHEMA else read(p, **kw)
        ),
    ):
        with pytest.raises(AppError):
            Project.open(path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT value FROM schema_meta").fetchone()[0] == "2"
        assert (
            db.execute("SELECT notes FROM projects").fetchone()[0]
            == "Committed history"
        )
    project = Project.open(path)
    assert (
        project.connection.execute("SELECT value FROM schema_meta").fetchone()[0] == "3"
    )
    project.close()
    # Existing backup from initial creation must not be overwritten.
    with sqlite3.connect(path.with_name("project.schema-v2.sqlite.bak")) as backup:
        assert backup.execute("SELECT value FROM schema_meta").fetchone()[0] == "2"


class ControlledDetector:
    detector_id = "audio.clipping"
    detector_version = "test"

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def supports(self, context: DetectorContext) -> bool:
        return True

    def analyze(self, context: DetectorContext) -> DetectorResult:
        self.calls += 1
        self.entered.set()
        while not self.release.wait(0.01):
            context.cancellation.check()
        return DetectorResult(metrics={})


def wait_batch(services: Projects) -> None:
    assert services.batches.worker is not None
    services.batches.worker.join(15)
    assert not services.batches.active


def test_discovery_pause_stop_and_reopen(tmp_path: Path) -> None:
    source = tmp_path / "sources"
    source.mkdir()
    for name in ("001.wav", "002.wav", "003.wav"):
        with wave.open(str(source / name), "wb") as output:
            output.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
            output.writeframes(b"\0" * 9600)
    (source / "notes.txt").write_text("unsupported")
    (source / "extra.flac").write_bytes(b"not auto-discovered")
    service = Projects()
    project = service.dispatch(
        "project.create",
        {
            "directory": str(tmp_path / "project"),
            "name": "Queue",
            "summary_mode": "compact",
        },
    )
    detector = ControlledDetector()
    service.jobs.detectors = (detector,)
    try:
        batch = service.dispatch(
            "batch.create",
            {
                "project_id": project["id"],
                "name": "Sources",
                "source_kind": "FOLDER",
                "absolute_path": str(source),
            },
        )
        identifier = batch["batch_id"]
        wait_batch(service)
        saved = service.dispatch("batch.get", {"batch_id": identifier})
        assert saved["counts"]["total"] == 3  # type: ignore[index]
        assert saved["import_summary"]["excluded"] == 2  # type: ignore[index]
        profile = profiles.builtin()
        service.dispatch(
            "batch.start",
            {
                "batch_id": identifier,
                "profile_key": profile["profile_key"],
                "profile_version": profile["version"],
                "ai_mode": "OFF",
            },
        )
        assert detector.entered.wait(8)
        service.dispatch("batch.pause", {"batch_id": identifier})
        assert (
            service.dispatch("batch.get", {"batch_id": identifier})["status"]
            == "PAUSING"
        )
        detector.release.set()
        wait_batch(service)
        assert detector.calls == 1
        assert (
            service.dispatch("batch.get", {"batch_id": identifier})["status"]
            == "PAUSED"
        )
        detector.release.clear()
        detector.entered.clear()
        service.dispatch("batch.resume", {"batch_id": identifier})
        assert detector.entered.wait(8)
        service.dispatch("batch.stop", {"batch_id": identifier})
        wait_batch(service)
        saved = service.dispatch("batch.get", {"batch_id": identifier})
        assert saved["status"] == "STOPPED"
        assert saved["counts"]["pass"] == 1  # type: ignore[index]
        assert saved["counts"]["cancelled"] == 2  # type: ignore[index]
        assert detector.calls == 2
    finally:
        service.close()


def test_queue_paging_exclusions_and_recovery(tmp_path: Path) -> None:
    project = Project.create(tmp_path / "project", "Queue")
    db = project.connection
    identifier = batches.create(db, project.id, "137 files", "FOLDER", str(tmp_path))
    for index in range(137):
        path = tmp_path / f"{index:03}.wav"
        batches.add_item(db, identifier, path, path.name)
    batches.add_item(db, identifier, tmp_path / "000.wav", "000.wav")
    batches.add_item(
        db, identifier, tmp_path / "notes.txt", "notes.txt", "UNSUPPORTED_EXTENSION"
    )
    batches.finish_import(db, identifier)
    assert batches.counts(db, identifier)["total"] == 137
    result = batches.items(db, {"batch_id": identifier, "offset": 100})
    assert len(result["items"]) == 37  # type: ignore[arg-type]
    imported = batches.items(db, {"batch_id": identifier, "filter": "IMPORT_RESULTS"})[
        "items"
    ]
    assert isinstance(imported, list) and len(imported) == 2
    assert db.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0] == 0
    first = db.execute("SELECT id FROM batch_items WHERE queue_position=1").fetchone()[
        0
    ]
    batches.state(db, identifier, "RUNNING")
    batches.update_item(db, first, "INSPECTING")
    batches.reconcile(db)
    assert batches.fetch(db, identifier)["status"] == "INTERRUPTED"
    assert batches.counts(db, identifier)["error"] == 1
    assert batches.counts(db, identifier)["pending"] == 136
    batches.state(db, identifier, "STOPPING")
    batches.reconcile(db)
    assert batches.fetch(db, identifier)["status"] == "STOPPED"
    assert batches.counts(db, identifier)["cancelled"] == 136
    project.close()


def test_real_137_file_queue_is_sequential_and_immutable(
    batch_session: tuple[Projects, Path, ControlledDetector],
) -> None:
    service, source, detector = batch_session
    for index in range(137):
        wav(source / f"{index:03}.wav")
    before = {
        p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
        for p in source.iterdir()
    }
    identifier = import_batch(service, source)
    assert service.project is not None
    db = service.project.connection
    assert db.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0] == 0
    start_batch(service, identifier)
    assert service.batches.worker is not None
    while service.batches.worker.is_alive():
        value = service.dispatch("batch.get", {"batch_id": identifier})
        assert cast(dict[str, int], value["counts"])["processing"] <= 1
        assert (
            db.execute(
                "SELECT COUNT(*) FROM analysis_runs WHERE status NOT IN "
                "('COMPLETED','FAILED','CANCELLED')"
            ).fetchone()[0]
            <= 1
        )
        service.batches.worker.join(0.05)
    assert detector.calls == 137
    assert batches.counts(db, identifier)["pass"] == 137
    assert {
        p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
        for p in source.iterdir()
    } == before


def test_corrupt_changed_and_explicit_extension(
    batch_session: tuple[Projects, Path, ControlledDetector],
) -> None:
    service, source, detector = batch_session
    wav(source / "good.WAV")
    (source / "bad.mp4").write_bytes(b"corrupt media")
    wav(source / "changed.wav")
    identifier = import_batch(service, source)
    (source / "changed.wav").write_bytes(b"changed")
    start_batch(service, identifier)
    wait_batch(service)
    assert service.project is not None
    count = batches.counts(service.project.connection, identifier)
    assert (count["pass"], count["error"]) == (1, 2)
    log = service.project.connection.execute(
        "SELECT log_reference FROM batch_items WHERE batch_id=? "
        "AND relative_path='bad.mp4'",
        (identifier,),
    ).fetchone()[0]
    assert "stderr_excerpt" in (service.project.path.parent / log).read_text()
    assert detector.calls == 1
    wav(source / "explicit.other")
    explicit = import_batch(service, source / "explicit.other", folder=False)
    start_batch(service, explicit)
    wait_batch(service)
    assert batches.counts(service.project.connection, explicit)["pass"] == 1


def test_subfolders_retry_and_reports(
    batch_session: tuple[Projects, Path, ControlledDetector],
) -> None:
    service, source, _ = batch_session
    (source / "sub").mkdir()
    wav(source / "root.wav")
    wav(source / "sub" / "nested.wav")
    (source / "bad.mp3").write_bytes(b"corrupt")
    first = import_batch(service, source)
    assert service.project is not None
    db = service.project.connection
    assert batches.counts(db, first)["total"] == 2
    identifier = import_batch(service, source, recursive=True)
    assert batches.counts(db, identifier)["total"] == 3
    start_batch(service, identifier)
    wait_batch(service)
    assert batches.counts(db, identifier)["error"] == 1
    for kind in ("HTML", "PDF"):
        response = service.dispatch(
            "batch.report.generate", {"batch_id": identifier, "format": kind}
        )
        output = Path(str(response["absolute_path"]))
        assert output.is_file()
        if kind == "HTML":
            assert "bad.mp3" in output.read_text(encoding="utf-8")
            assert "No QC verdict" in output.read_text(encoding="utf-8")
    retry = service.dispatch(
        "batch.retry", {"batch_id": identifier, "selection": "ERROR"}
    )
    wait_batch(service)
    assert batches.counts(db, str(retry["batch_id"]))["total"] == 1
    assert batches.counts(db, identifier)["pass"] == 2
    assert db.execute("SELECT COUNT(*) FROM batch_reports").fetchone()[0] == 2


@pytest.mark.parametrize("completion", [False, True])
def test_recovery_reconciles_linked_run_and_preserves_pending(
    batch_session: tuple[Projects, Path, ControlledDetector], completion: bool
) -> None:
    service, source, _ = batch_session
    wav(source / "first.wav")
    wav(source / "second.wav")
    identifier = import_batch(service, source)
    assert service.project is not None
    db = service.project.connection
    profile = profiles.builtin()
    with db:
        db.execute(
            "UPDATE batches SET status='RUNNING',profile_key=?,profile_version=?,"
            "qc_profile_snapshot_json=? WHERE id=?",
            (
                profile["profile_key"],
                profile["version"],
                runs.encode(profile),
                identifier,
            ),
        )
    item = db.execute(
        "SELECT id FROM batch_items WHERE batch_id=? ORDER BY queue_position LIMIT 1",
        (identifier,),
    ).fetchone()[0]
    batches.update_item(db, item, "INSPECTING")
    asset = service.dispatch(
        "media.inspect",
        {"project_id": service.project.id, "absolute_path": str(source / "first.wav")},
    )
    run = runs.create(
        db,
        service.project.id,
        str(asset["media_asset_id"]),
        profile,
        None,
        batch_item_id=item,
    )
    if completion:
        runs.transition(db, run, "INSPECTING")
        runs.transition(db, run, "ANALYZING")
        runs.transition(db, run, "COMPLETED")
    path = service.project.path
    service.close_project()
    service.dispatch(
        "project.open", {"project_file": str(path), "summary_mode": "compact"}
    )
    value = service.dispatch("batch.get", {"batch_id": identifier})
    assert value["status"] == "INTERRUPTED"
    assert value["can_continue_pending"] is True
    counts = cast(dict[str, int], value["counts"])
    assert counts["pending"] == 1
    assert counts["pass" if completion else "error"] == 1
    service.dispatch("batch.resume", {"batch_id": identifier})
    wait_batch(service)
    assert (
        service.dispatch("batch.get", {"batch_id": identifier})["status"] == "COMPLETED"
    )


def test_atomic_run_link_rolls_back_on_invalid_item(
    batch_session: tuple[Projects, Path, ControlledDetector],
) -> None:
    service, source, _ = batch_session
    wav(source / "file.wav")
    assert service.project is not None
    asset = service.dispatch(
        "media.inspect",
        {"project_id": service.project.id, "absolute_path": str(source / "file.wav")},
    )
    with pytest.raises(AppError, match="cannot start"):
        runs.create(
            service.project.connection,
            service.project.id,
            str(asset["media_asset_id"]),
            profiles.builtin(),
            None,
            batch_item_id="missing",
        )
    assert (
        service.project.connection.execute(
            "SELECT COUNT(*) FROM analysis_runs"
        ).fetchone()[0]
        == 0
    )


@pytest.mark.parametrize(
    "measured,difference", [(-24.12, 0.12), (-24, 0), (-21.9, 0.1)]
)
def test_explanation_preserves_values(measured: float, difference: float) -> None:
    finding: dict[str, object] = {
        "detector_id": "audio.loudness.integrated",
        "description": "Saved finding",
        "measurements": {"integrated_lufs": measured},
        "threshold": {"target_lufs": -23, "tolerance_lu": 1},
        "severity": "WARN",
    }
    before = json.dumps(finding)
    value = explain(finding)
    comparison = cast(list[dict[str, object]], value["comparisons"])[0]
    assert comparison["minimum"] == -24
    assert comparison["maximum"] == -22
    assert comparison["difference_from_limit"] == difference
    assert json.dumps(finding) == before


def test_missing_tools_halts_queue(
    batch_session: tuple[Projects, Path, ControlledDetector], tmp_path: Path
) -> None:
    service, source, detector = batch_session
    wav(source / "a.wav")
    wav(source / "b.wav")
    identifier = import_batch(service, source)
    service.jobs.tool_factory = lambda: MediaTools(directory=tmp_path / "missing")
    start_batch(service, identifier)
    wait_batch(service)
    value = service.dispatch("batch.get", {"batch_id": identifier})
    assert value["status"] == "FAILED"
    assert cast(dict[str, int], value["counts"])["pending"] == 1
    assert detector.calls == 0


def test_links_partial_import_and_exact_extensions(
    batch_session: tuple[Projects, Path, ControlledDetector],
) -> None:
    from mediaqc_engine.jobs import discovery

    service, source, _ = batch_session
    for extension in ("wav", "MP3", "mp4", "mxf", "mov", "aif", "aiff", "flac", "aac"):
        (source / f"file.{extension}").write_bytes(b"candidate")
    (source / "junction").mkdir()
    wav(source / "junction" / "hidden.wav")
    (source / "denied").mkdir()
    scan = os.scandir

    def guarded(path: Path) -> object:
        if Path(path).name == "denied":
            raise PermissionError("test unreadable directory")
        return scan(path)

    with (
        patch.object(discovery, "linked", side_effect=lambda p: p.name == "junction"),
        patch.object(os, "scandir", side_effect=guarded),
    ):
        identifier = import_batch(service, source, recursive=True)
    value = service.dispatch("batch.get", {"batch_id": identifier})
    assert cast(dict[str, int], value["counts"])["total"] == 4
    imported = cast(dict[str, object], value["import_summary"])
    assert imported["partial"] is True and imported["excluded"] == 7
    with patch.object(discovery, "linked", return_value=True):
        linked_root = import_batch(service, source)
    value = service.dispatch("batch.get", {"batch_id": linked_root})
    assert cast(dict[str, int], value["counts"])["total"] == 0


@pytest.mark.parametrize("params", [{"limit": 51}, {"offset": -1}, {"limit": True}])
def test_pagination_rejects_unbounded_requests(params: dict[str, object]) -> None:
    with pytest.raises(AppError):
        batches.page(params)


def test_real_mixed_core_formats(
    batch_session: tuple[Projects, Path, ControlledDetector],
) -> None:
    from generate_test_media.video import generate

    service, source, detector = batch_session
    wav(source / "audio.wav")
    tool = MediaTools()
    tool.run(
        "ffmpeg",
        [
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(source / "audio.wav"),
            str(source / "audio.mp3"),
        ],
    )
    generate("video.clean.001", source, ".mp4")
    generate("video.clean.001", source, ".mxf")
    identifier = import_batch(service, source)
    start_batch(service, identifier)
    wait_batch(service)
    value = service.dispatch("batch.get", {"batch_id": identifier})
    assert cast(dict[str, int], value["counts"])["pass"] == 4
    assert detector.calls == 4


def test_stop_after_127_preserves_history_and_ownership(
    batch_session: tuple[Projects, Path, ControlledDetector],
) -> None:
    service, source, detector = batch_session
    for index in range(150):
        wav(source / f"{index:03}.wav")
    identifier = import_batch(service, source)
    probe = MediaTools().probe(source / "000.wav")
    reached = threading.Event()
    analyze = detector.analyze

    def controlled(context: DetectorContext) -> DetectorResult:
        if detector.calls == 127:
            detector.release.clear()
            reached.set()
        return analyze(context)

    with (
        patch.object(MediaTools, "probe", return_value=probe),
        patch.object(detector, "analyze", side_effect=controlled),
    ):
        start_batch(service, identifier)
        assert reached.wait(30)
        for method, params in (
            ("analysis.cancel", {"analysis_run_id": service.jobs.identifier}),
            ("media.inspect", {}),
            ("project.open", {}),
            ("report.generate", {}),
        ):
            with pytest.raises(AppError, match="batch controls"):
                service.dispatch(method, cast(dict[str, object], params))
        service.dispatch("batch.stop", {"batch_id": identifier})
        wait_batch(service)
    value = service.dispatch("batch.get", {"batch_id": identifier})
    counts = cast(dict[str, int], value["counts"])
    assert (counts["pass"], counts["cancelled"], counts["pending"]) == (127, 23, 0)
    assert service.project is not None
    assert (
        service.project.connection.execute(
            "SELECT COUNT(*) FROM analysis_runs"
        ).fetchone()[0]
        == 128
    )


def test_stop_after_run_commit_preserves_completed_item(
    batch_session: tuple[Projects, Path, ControlledDetector],
) -> None:
    service, source, _ = batch_session
    wav(source / "first.wav")
    wav(source / "second.wav")
    identifier = import_batch(service, source)
    committed, release = threading.Event(), threading.Event()
    finish = service.jobs.finish

    def delayed(*args: object, **kwargs: object) -> None:
        finish(*args, **kwargs)  # type: ignore[arg-type]
        committed.set()
        assert release.wait(10)

    with patch.object(service.jobs, "finish", side_effect=delayed):
        start_batch(service, identifier)
        try:
            assert committed.wait(10)
            service.dispatch("batch.stop", {"batch_id": identifier})
        finally:
            release.set()
        wait_batch(service)
    value = service.dispatch("batch.get", {"batch_id": identifier})
    counts = cast(dict[str, int], value["counts"])
    assert (counts["pass"], counts["cancelled"]) == (1, 1)


def test_storage_failure_halts_and_surfaces_unpersisted_failure(
    batch_session: tuple[Projects, Path, ControlledDetector],
) -> None:
    service, source, detector = batch_session
    wav(source / "one.wav")
    wav(source / "two.wav")
    identifier = import_batch(service, source)
    events: list[tuple[str, dict[str, object]]] = []
    service.batches.emit = lambda event, data: events.append((event, data))
    entered, release = threading.Event(), threading.Event()
    original_state = batches.state

    def failure(*args: object, **kwargs: object) -> None:
        entered.set()
        assert release.wait(10)
        raise sqlite3.OperationalError("disk full")

    def failed_state(
        db: sqlite3.Connection,
        key: str,
        status: str,
        code: str | None = None,
        message: str | None = None,
    ) -> None:
        if status == "FAILED":
            raise sqlite3.OperationalError("disk full")
        original_state(db, key, status, code, message)

    with patch.object(batches, "update_item", side_effect=failure):
        start_batch(service, identifier)
        try:
            assert entered.wait(10)
            with patch.object(batches, "state", side_effect=failed_state):
                release.set()
                wait_batch(service)
        finally:
            release.set()
    assert detector.calls == 0
    assert any(
        event == "batch.failed" and data["error_code"] == "PROJECT_INVALID"
        for event, data in events
    )
    value = service.dispatch("batch.get", {"batch_id": identifier})
    assert value["status"] == "FAILED" and value["error_code"] == "PROJECT_INVALID"
    assert cast(dict[str, int], value["counts"])["pending"] == 2
    with pytest.raises(AppError, match="Restart and reopen"):
        service.batches.available()
    with pytest.raises(AppError, match="Restart and reopen"):
        service.dispatch("analysis.start", {})


@pytest.mark.parametrize(
    "detector,metric,policy,measured,difference",
    [
        ("audio.true_peak", "true_peak_dbtp", {"max_dbtp": -1}, -0.9, 0.1),
        (
            "audio.phase_correlation",
            "correlation_coefficient",
            {"min_correlation": -0.25},
            -0.8,
            0.55,
        ),
        (
            "audio.noise_floor",
            "estimated_noise_floor_dbfs",
            {"max_estimated_noise_floor_dbfs": -45},
            -42,
            3,
        ),
        ("audio.loudness.short_term", "short_term_lufs", {"max_lufs": -10}, -9, 1),
        (
            "video.frame_rate",
            "measured_fps",
            {"expected_fps": 25, "tolerance_fps": 0.1},
            24,
            0.9,
        ),
    ],
)
def test_saved_threshold_adapters(
    detector: str,
    metric: str,
    policy: dict[str, float],
    measured: float,
    difference: float,
) -> None:
    value = explain(
        {
            "detector_id": detector,
            "measurements": {metric: measured},
            "threshold": policy,
        }
    )
    comparison = cast(list[dict[str, object]], value["comparisons"])[0]
    assert comparison["measured"] == measured
    assert comparison["difference_from_limit"] == difference


def test_disposition_refreshes_batch_filter_counts_and_revision(
    batch_session: tuple[Projects, Path, ControlledDetector],
) -> None:
    service, source, _ = batch_session
    wav(source / "one.wav")
    identifier = import_batch(service, source)
    start_batch(service, identifier)
    wait_batch(service)
    assert service.project is not None
    db = service.project.connection
    run, execution = db.execute(
        "SELECT analysis_run_id,id FROM detector_executions LIMIT 1"
    ).fetchone()
    finding = str(uuid4())
    with db:
        findings.save(
            db,
            service.project.path.parent,
            run,
            execution,
            {
                "id": finding,
                "detector_id": "audio.clipping",
                "detector_version": "test",
                "stream_id": None,
                "severity": "FAIL",
                "confidence": None,
                "start_time_seconds": 0,
                "end_time_seconds": 0.01,
                "duration_seconds": 0.01,
                "title": "Clipping",
                "description": "Saved test finding",
                "disposition": "OPEN",
                "measurements": {"sample_peak_dbfs": 0},
                "threshold": {"near_full_scale_dbfs": -0.01},
                "metadata": {},
            },
        )
        db.execute("UPDATE analysis_runs SET overall_result='FAIL' WHERE id=?", (run,))
    before = service.dispatch("batch.get", {"batch_id": identifier})
    assert (
        batches.items(db, {"batch_id": identifier, "filter": "NEEDS_ATTENTION"})[
            "total"
        ]
        == 1
    )
    service.dispatch(
        "finding.set_disposition",
        {
            "finding_id": finding,
            "disposition": "FALSE_POSITIVE",
            "note": "Intentional sound",
        },
    )
    after = service.dispatch("batch.get", {"batch_id": identifier})
    assert int(str(after["revision"])) == int(str(before["revision"])) + 1
    assert cast(dict[str, int], after["counts"])["pass"] == 1
    assert (
        batches.items(db, {"batch_id": identifier, "filter": "NEEDS_ATTENTION"})[
            "total"
        ]
        == 0
    )
    assert service.dispatch("finding.get", {"finding_id": finding})["measurements"] == {
        "sample_peak_dbfs": 0
    }


@pytest.mark.parametrize("value", [None, float("nan"), float("inf")])
def test_explanations_do_not_invent_missing_measurements(value: float | None) -> None:
    explained = explain(
        {
            "detector_id": "audio.true_peak",
            "description": "Saved explanation",
            "measurements": {"true_peak_dbtp": value},
            "threshold": {"max_dbtp": -1},
        }
    )
    assert explained == {"summary": "Saved explanation", "comparisons": []}
    json.dumps(explained, allow_nan=False)
