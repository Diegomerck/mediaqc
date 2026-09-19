"""Saved-data exports, no decoder/network/source dependency."""

import hashlib
import json
import socket
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import pytest
from pypdf import PdfReader

from mediaqc_engine import reports
from mediaqc_engine.app.errors import AppError
from mediaqc_engine.app.projects import Projects
from mediaqc_engine.db import findings, runs
from mediaqc_engine.db.project import Project
from mediaqc_engine.ipc.server import handle_line
from mediaqc_engine.qc import profiles


@pytest.fixture
def saved(tmp_path: Path) -> Iterator[tuple[Projects, str, Path]]:
    source = tmp_path / "source 音楽 é &.wav"
    source.write_bytes(b"immutable media fixture")
    before = source.read_bytes(), source.stat().st_mtime_ns
    service = Projects(state_directory=tmp_path / "state")
    project = Project.create(
        tmp_path / "project", "Review <script>alert(1)</script> & é 音楽"
    )
    service.project = project
    asset = project.save_media(
        {
            "absolute_path": str(source),
            "file_name": source.name,
            "file_size_bytes": source.stat().st_size,
            "inspection_status": "COMPLETED",
            "fast_fingerprint_sha256": "saved-fingerprint",
            "duration_seconds": 5.0,
        },
        [],
    )
    run = runs.create(
        project.connection, project.id, asset, profiles.builtin(), "saved-fingerprint"
    )
    with project.connection:
        project.connection.execute(
            "UPDATE analysis_runs SET engine_version='saved-engine',"
            "ffmpeg_version='saved-ffmpeg' WHERE id=?",
            (run,),
        )
        execution = str(uuid4())
        project.connection.execute(
            "INSERT INTO detector_executions "
            "(id,analysis_run_id,detector_id,detector_version,status) "
            "VALUES (?,?,?,'saved-detector','COMPLETED')",
            (execution, run, "audio.clipping"),
        )
        for severity in ("INFO", "WARN", "FAIL"):
            findings.save(
                project.connection,
                project.path.parent,
                run,
                execution,
                {
                    "id": str(uuid4()),
                    "detector_id": "audio.clipping",
                    "detector_version": "saved-detector",
                    "stream_id": None,
                    "severity": severity,
                    "confidence": None,
                    "start_time_seconds": 1.0,
                    "end_time_seconds": 2.0,
                    "duration_seconds": 1.0,
                    "title": "<b>Issue</b> & é 音楽",
                    "description": "Saved finding",
                    "disposition": "OPEN",
                    "measurements": {"peak": 2},
                    "threshold": {"limit": 1},
                    "metadata": {},
                },
            )
    runs.transition(project.connection, run, "INSPECTING")
    runs.transition(project.connection, run, "ANALYZING")
    runs.transition(project.connection, run, "COMPLETED")
    siblings = sorted(tmp_path.iterdir())
    try:
        yield service, run, source
    finally:
        service.close()
        assert before == (source.read_bytes(), source.stat().st_mtime_ns)
        assert sorted(tmp_path.iterdir()) == siblings


def export(service: Projects, run: str, kind: str) -> Path:
    response, _ = handle_line(
        json.dumps(
            {
                "type": "request",
                "protocol_version": "1.0",
                "request_id": str(uuid4()),
                "method": "report.generate",
                "params": {"analysis_run_id": run, "format": kind},
            }
        ).encode(),
        service,
    )
    assert response and response["ok"], response
    return Path(str(cast(dict[str, object], response["result"])["absolute_path"]))


@pytest.mark.parametrize("kind", ["HTML", "PDF"])
def test_offline_reopen_reproducible(
    saved: tuple[Projects, str, Path], kind: str
) -> None:
    service, run, source = saved
    assert service.project
    project_file = service.project.path
    with (
        patch.object(socket, "socket", side_effect=AssertionError("network")),
        patch.object(subprocess, "Popen", side_effect=AssertionError("subprocess")),
        patch(
            "mediaqc_engine.media.inspection.fingerprint",
            side_effect=AssertionError("source opened"),
        ),
    ):
        first = export(service, run, kind)
        service.close_project()
        service.project = Project.open(project_file)
        second = export(service, run, kind)
    assert first != second
    assert first.read_bytes() == second.read_bytes()
    if kind == "HTML":
        text = first.read_text(encoding="utf-8")
        assert "<script>alert" not in text and "&lt;script&gt;" in text
        assert "音楽" in text and "&amp;" in text
    else:
        reader = PdfReader(first)
        text = "\n".join(page.extract_text() for page in reader.pages)
        assert "é" in text and r"\u97f3" in text
        assert len(reader.pages) > 1
    for value in (
        run,
        "saved-engine",
        "saved-detector",
        "saved-ffmpeg",
        "saved-fingerprint",
        "1.2.0",
        "FAIL",
        "WARN",
        "INFO",
        "OPEN",
        "AVAILABLE",
        "measurements",
        "threshold",
    ):
        assert value in text
    assert (
        service.project.connection.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        == 2
    )
    # A missing source is irrelevant to the report and cannot initiate a QC rerun.
    with patch.object(
        Path,
        "open",
        autospec=True,
        side_effect=lambda path, *args, **kwargs: (
            (_ for _ in ()).throw(AssertionError("source"))
            if path == source
            else original_open(path, *args, **kwargs)
        ),
    ):
        assert export(service, run, kind).read_bytes() == first.read_bytes()


original_open = Path.open


@pytest.mark.parametrize(
    ("disposition", "expected"),
    [
        ("OPEN", "FAIL"),
        ("CONFIRMED", "FAIL"),
        ("FALSE_POSITIVE", "PASS"),
        ("IGNORED", "PASS"),
    ],
)
def test_disposition(
    saved: tuple[Projects, str, Path], disposition: str, expected: str
) -> None:
    service, run, _ = saved
    assert service.project
    db = service.project.connection
    for row in db.execute("SELECT id FROM findings").fetchall():
        service.dispatch(
            "finding.set_disposition",
            {
                "finding_id": row[0],
                "disposition": disposition,
                "note": "Operator <review>",
            },
        )
    data = reports.sections(service.project, run)
    assert data[0] == ("Overall result", expected)
    assert disposition in str(data) and "Operator <review>" in str(data)
    assert sum(title.startswith("Finding ") for title, _ in data) == 3


def test_warn_missing_stale_and_pagination(saved: tuple[Projects, str, Path]) -> None:
    service, run, _ = saved
    assert service.project
    db = service.project.connection
    fail = db.execute("SELECT id FROM findings WHERE severity='FAIL'").fetchone()[0]
    service.dispatch(
        "finding.set_disposition", {"finding_id": fail, "disposition": "IGNORED"}
    )
    items = db.execute("SELECT relative_path FROM evidence ORDER BY rowid").fetchall()
    (service.project.path.parent / items[0][0]).unlink()
    (service.project.path.parent / items[1][0]).write_text("{}", encoding="utf-8")
    assert reports.sections(service.project, run)[0] == ("Overall result", "WARN")
    text = export(service, run, "HTML").read_text(encoding="utf-8")
    assert "UNAVAILABLE" in text and "STALE" in text
    with db:
        row = dict(db.execute("SELECT * FROM findings LIMIT 1").fetchone())
        for _ in range(101):
            row["id"] = str(uuid4())
            db.execute(
                f"INSERT INTO findings ({','.join(row)}) "
                f"VALUES ({','.join('?' for _ in row)})",
                tuple(row.values()),
            )
    assert "Finding 104:" in export(service, run, "HTML").read_text(encoding="utf-8")


def test_failure_cleanup_and_limits(saved: tuple[Projects, str, Path]) -> None:
    service, run, _ = saved
    assert service.project
    for params in (
        {"analysis_run_id": run, "format": "PNG"},
        {"analysis_run_id": run, "format": []},
        {"format": "PDF"},
    ):
        with pytest.raises(AppError, match="Specify"):
            service.dispatch("report.generate", cast(dict[str, object], params))
    with patch.object(reports, "write_pdf", side_effect=OSError("disk full")):
        with pytest.raises(AppError) as error:
            service.dispatch(
                "report.generate", {"analysis_run_id": run, "format": "PDF"}
            )
        assert error.value.code == "REPORT_FAILED"
    assert not list((service.project.path.parent / "reports").iterdir())
    assert (
        service.project.connection.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        == 0
    )
    with (
        patch.object(reports, "MAX_FINDINGS", 2),
        pytest.raises(AppError, match="limit"),
    ):
        reports.sections(service.project, run)
    with (
        patch.object(reports, "MAX_TEXT_BYTES", 10),
        pytest.raises(AppError, match="limit"),
    ):
        reports.sections(service.project, run)
    with service.project.connection:
        service.project.connection.execute(
            "UPDATE analysis_runs SET status='FAILED' WHERE id=?", (run,)
        )
    with pytest.raises(AppError, match="completed"):
        reports.sections(service.project, run)


def test_visual_evidence_checksum(saved: tuple[Projects, str, Path]) -> None:
    service, _, _ = saved
    assert service.project
    root = service.project.path.parent
    path = root / "evidence/video/frame.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    item: dict[str, object] = {
        "relative_path": "evidence/video/frame.png",
        "mime_type": "image/png",
        "metadata_json": json.dumps(
            {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        ),
    }
    assert reports.evidence_status(root, item, {}).startswith("AVAILABLE")
    path.write_bytes(b"altered")
    assert reports.evidence_status(root, item, {}).startswith("STALE")
    item["relative_path"] = "../source.wav"
    assert reports.evidence_status(root, item, {}).startswith("UNAVAILABLE")


def test_clean_pass_and_missing_source(saved: tuple[Projects, str, Path]) -> None:
    service, run, _ = saved
    assert service.project
    db = service.project.connection
    with db:
        db.execute("DELETE FROM findings")
        db.execute("UPDATE analysis_runs SET overall_result='PASS'")
        db.execute("UPDATE media_assets SET absolute_path='Z:/missing/source.wav'")
    assert reports.sections(service.project, run)[0] == ("Overall result", "PASS")
    assert export(service, run, "PDF").is_file()


def test_database_failure_cleans_export(saved: tuple[Projects, str, Path]) -> None:
    service, run, _ = saved
    assert service.project
    with service.project.connection:
        service.project.connection.execute(
            "CREATE TRIGGER reject_report BEFORE INSERT ON reports "
            "BEGIN SELECT RAISE(ABORT, 'fixture database failure'); END"
        )
    with pytest.raises(AppError) as error:
        service.dispatch("report.generate", {"analysis_run_id": run, "format": "HTML"})
    assert error.value.code == "REPORT_FAILED"
    assert not list((service.project.path.parent / "reports").iterdir())
