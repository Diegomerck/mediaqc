"""Focused runtime assignment, channel silence, source identity and routing gates."""

import hashlib
import html
import json
import sqlite3
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from generate_test_media.audio import generate
from pypdf import PdfReader

from mediaqc_engine.app.projects import Projects
from mediaqc_engine.db.project import Project
from mediaqc_engine.detectors.audio.levels import LevelDetector
from mediaqc_engine.detectors.audio.loudness import LoudnessDetector
from mediaqc_engine.jobs.cancellation import CancellationToken, Cancelled
from mediaqc_engine.qc.audio_applicability import source_digest


@pytest.mark.parametrize("declared", [False, True])
def test_scoped_report_preserves_assignment_after_reopen(
    tmp_path: Path, declared: bool
) -> None:
    from mediaqc_engine import reports

    source = generate("audio.production_multitrack.001", tmp_path)
    services, asset = setup(tmp_path, source)
    services.jobs.detectors = (LevelDetector("audio.silence"),)
    doc = assignment(source)
    if not declared:
        doc["channels"] = []
        doc["programs"] = []
    try:
        run = start(services, asset, doc)
        result = finish(services, run)
        assert result["status"] == "COMPLETED", result
        assert result["overall_result"] == "PASS"
        assert services.project
        path = services.project.path
    finally:
        services.close()
    project = Project.open(path)
    before = digest(source), source.stat().st_mtime_ns
    try:
        content = reports.sections(project, run)
        saved = json.loads(dict(content)["Saved audio applicability"])
        assert saved["document"] == doc
        assert saved["source_sha256"] == doc["source_sha256"]
        assert saved["policy_version"] == "explicit_audio_v1"
        assert len(saved["channels"]) == 7
        assert [c["expectation"] for c in saved["channels"]] == (
            [c["expectation"] for c in doc["channels"]] if declared else ["unknown"] * 7
        )
        if declared:
            assert saved["programs"][0]["members"] == [[0, 0], [0, 1]]
        else:
            assert saved["programs"] == []
            assert "No audio program is designated" in str(content)
        for kind in ("html", "pdf"):
            output = tmp_path / ("assignment." + kind)
            if kind == "html":
                reports.write_html(output, content)
                text = html.unescape(output.read_text(encoding="utf-8"))
            else:
                reports.write_pdf(output, content)
                text = "\n".join(p.extract_text() for p in PdfReader(output).pages)
            assert "Saved audio applicability" in text
            assert saved["identity"] in text
            assert doc["source_sha256"] in text
            assert "unknown" in text
    finally:
        project.close()
    assert before == (digest(source), source.stat().st_mtime_ns)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assignment(source: Path, mxf: bool = False) -> dict[str, Any]:
    members = [[i, 0] for i in range(1, 9)] if mxf else [[0, i] for i in range(7)]
    return {
        "schema_version": "0.1.0",
        "source_sha256": digest(source),
        "provenance": "synthetic-owner-review",
        "channels": [
            {
                "member": m,
                "role": "mix" if i < 2 else "iso",
                "expectation": "expected"
                if i < 3
                else "unused"
                if i % 2
                else "unknown",
            }
            for i, m in enumerate(members)
        ],
        "programs": [{"program_id": "L/R", "layout": "stereo", "members": members[:2]}],
    }


def start(services: Projects, asset: str, document: dict[str, Any]) -> str:
    assert services.project
    result = services.dispatch(
        "analysis.start",
        {
            "project_id": services.project.id,
            "media_asset_id": asset,
            "profile_key": "general_technical_qc",
            "profile_version": "1.2.0",
            "ai_mode": "OFF",
            "audio_assignment": document,
        },
    )
    return str(result["analysis_run_id"])


def finish(services: Projects, run: str) -> dict[str, Any]:
    assert services.jobs.worker
    services.jobs.worker.join(30)
    assert not services.jobs.active
    return services.dispatch("analysis.get", {"analysis_run_id": run})


def setup(tmp_path: Path, source: Path) -> tuple[Projects, str]:
    services = Projects(state_directory=tmp_path / "state")
    project = services.dispatch(
        "project.create",
        {"directory": str(tmp_path / "project"), "name": "Scoped audio"},
    )
    asset = services.dispatch(
        "media.inspect", {"project_id": project["id"], "absolute_path": str(source)}
    )
    return services, str(asset["media_asset_id"])


def test_runtime_channel_silence_retry_reopen_and_immutable_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mediaqc_engine.media.tools import MediaTools

    filters: list[str] = []
    original_run = MediaTools.run

    def record(self: MediaTools, tool: str, arguments: list[str]) -> bytes:
        if "-filter_complex" in arguments:
            filters.append(arguments[arguments.index("-filter_complex") + 1])
        return original_run(self, tool, arguments)

    monkeypatch.setattr(MediaTools, "run", record)
    source = tmp_path / "required-and-unused.wav"
    count = 100001  # rounded EOF duration reproduces the accepted 1.0.1 regression.
    audio = np.zeros((count, 7))
    audio[:, :2] = (0.1 * np.sin(2 * np.pi * 1000 * np.arange(count) / 48000))[:, None]
    with wave.open(str(source), "wb") as output:
        output.setparams((7, 2, 48000, 0, "NONE", "not compressed"))
        output.writeframes((audio * 32768).astype("<i2").tobytes())
    original = digest(source), source.stat().st_mtime_ns
    services, asset = setup(tmp_path, source)
    services.jobs.detectors = (LevelDetector("audio.silence"),)
    document = assignment(source)
    saved = json.loads(json.dumps(document))
    try:
        run = start(services, asset, document)
        document["channels"][2]["expectation"] = "unused"
        result = finish(services, run)
        assert result["status"] == "COMPLETED", result
        assert result["overall_result"] == "WARN"
        assert result["audio_assignment"] == saved
        assert services.project
        db = services.project.connection
        rows = db.execute(
            "SELECT * FROM findings WHERE analysis_run_id=?", (run,)
        ).fetchall()
        assert len(rows) == 5
        for row in rows:
            measured = json.loads(row["measurements_json"])
            channel = measured["channel_indices"][0]
            assert row["severity"] == ("WARN" if channel == 2 else "INFO")
            assert row["end_time_seconds"] == pytest.approx(
                count / 48000, abs=1 / 48000
            )
            assert measured["measurement_scope"]["members"] == [[0, channel]]
            assert json.loads(row["metadata_json"])["policy_severity"] == "WARN"
        with pytest.raises(sqlite3.IntegrityError, match="Immutable"):
            db.execute(
                "UPDATE audio_assignment_channels SET expectation='unused' "
                "WHERE analysis_run_id=?",
                (run,),
            )
        db.rollback()
        retry = services.dispatch("analysis.retry", {"analysis_run_id": run})
        assert (
            finish(services, str(retry["analysis_run_id"]))["audio_assignment"] == saved
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM findings WHERE analysis_run_id=?", (run,)
            ).fetchone()[0]
            == 5
        )
        path = services.project.path
    finally:
        services.close()
    reopened = Project.open(path)
    try:
        assert (
            reopened.connection.execute(
                "SELECT COUNT(*) FROM audio_assignments"
            ).fetchone()[0]
            == 2
        )
    finally:
        reopened.close()
    assert original == (digest(source), source.stat().st_mtime_ns)
    for channel in range(2, 7):
        assert any(f"pan=mono|c0=c{channel}" in graph for graph in filters)


@pytest.mark.parametrize("mxf", [False, True])
def test_runtime_program_scope_and_retained_raw_measurements(
    tmp_path: Path, mxf: bool
) -> None:
    source = generate(
        "audio.discontinuity.mxf_click.001"
        if mxf
        else "audio.production_multitrack.001",
        tmp_path,
    )
    services, asset = setup(tmp_path, source)
    services.jobs.detectors = (
        LoudnessDetector("audio.loudness.integrated"),
        LoudnessDetector("audio.loudness.momentary"),
    )
    before = digest(source)
    try:
        result = finish(services, start(services, asset, assignment(source, mxf)))
        assert result["status"] == "COMPLETED", result
        executions = result["detector_states"]
        integrated = json.loads(executions[0]["metrics_json"])
        assert len(integrated["streams"]) == (8 if mxf else 1)
        program = next(iter(integrated["programs"].values()))
        assert program["measurement_scope"]["members"] == (
            [[1, 0], [2, 0]] if mxf else [[0, 0], [0, 1]]
        )
        # Same synthetic 0.1-amplitude L/R tone. Different ISOs cannot alter it.
        from audio_reference_probe import program_loudness

        from mediaqc_engine.media.tools import MediaTools

        tools = MediaTools(cache=tmp_path / "control")
        stereo = generate(
            "audio.discontinuity.simultaneous.001", tmp_path / "control-source"
        )
        try:
            expected = program_loudness(tools, stereo, "[0:0]asetpts=PTS-STARTPTS")["I"]
            assert program["integrated_lufs"] == pytest.approx(expected, abs=0.01)
        finally:
            tools.cancel()
        assert services.project
        rows = services.project.connection.execute(
            "SELECT stream_id,severity,metadata_json,measurements_json FROM findings"
        ).fetchall()
        assert rows
        for stream_id, severity, metadata, measured in rows:
            if stream_id is not None:
                assert severity == "INFO"
                assert (
                    json.loads(metadata)["applicability"] == "UNASSIGNED_PROGRAM_SCOPE"
                )
            else:
                assert json.loads(measured)["measurement_scope"]["kind"] == "program"
        assert digest(source) == before
    finally:
        services.close()


def test_stale_assignment_fails_before_measurement(tmp_path: Path) -> None:
    source = generate("audio.production_multitrack.001", tmp_path)
    services, asset = setup(tmp_path, source)
    services.jobs.detectors = (LevelDetector("audio.silence"),)
    document = assignment(source)
    document["source_sha256"] = "0" * 64
    try:
        result = finish(services, start(services, asset, document))
        assert result["status"] == "FAILED"
        assert result["error_code"] == "MEDIA_CHANGED"
        assert result["overall_result"] is None
        assert not result["detector_states"]
    finally:
        services.close()


def test_source_hash_is_cancellable(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"test")
    token = CancellationToken()
    token.cancel()
    with pytest.raises(Cancelled):
        source_digest(source, token)


@pytest.mark.parametrize("required_iso", [False, True])
def test_mxf_unused_is_explicit_and_required_iso_still_warns(
    tmp_path: Path, required_iso: bool
) -> None:
    source = generate("audio.discontinuity.mxf_click.001", tmp_path)
    before = digest(source)
    services, asset = setup(tmp_path, source)
    services.jobs.detectors = (LevelDetector("audio.silence"),)
    doc = assignment(source, True)
    for channel in doc["channels"][2:]:
        channel["expectation"] = "unused"
    if required_iso:
        doc["channels"][2]["expectation"] = "expected"
    try:
        result = finish(services, start(services, asset, doc))
        assert result["status"] == "COMPLETED", result
        assert result["overall_result"] == ("WARN" if required_iso else "PASS")
        assert services.project
        rows = services.project.connection.execute(
            "SELECT severity,measurements_json FROM findings"
        ).fetchall()
        assert len(rows) == 6
        assert sum(row[0] == "WARN" for row in rows) == int(required_iso)
        assert {
            json.loads(row[1])["measurement_scope"]["members"][0][0] for row in rows
        } == set(range(3, 9))
        assert digest(source) == before
    finally:
        services.close()


def test_schema4_rollback_and_history_preservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mediaqc_engine.app.errors import AppError
    from mediaqc_engine.db import runs
    from mediaqc_engine.db.project import AUDIO_SCHEMA
    from mediaqc_engine.qc.profiles import builtin

    source = generate("audio.production_multitrack.001", tmp_path)
    services, asset = setup(tmp_path, source)
    assert services.project
    project = services.project
    db = project.connection
    run = runs.create(db, project.id, asset, builtin(), "legacy-fingerprint")
    for state in ("INSPECTING", "ANALYZING", "COMPLETED"):
        runs.transition(db, run, state)
    original = runs.fetch(db, run)
    with db:
        for table in (
            "audio_assignment_members",
            "audio_assignment_programs",
            "audio_assignment_channels",
            "audio_assignments",
        ):
            db.execute(f"DROP TABLE {table}")
        db.execute("UPDATE schema_meta SET value='3'")
    path = project.path
    services.close()
    original_read = Path.read_text
    with monkeypatch.context() as patcher:
        patcher.setattr(
            Path,
            "read_text",
            lambda p, **kw: (
                "INVALID SQL" if p == AUDIO_SCHEMA else original_read(p, **kw)
            ),
        )
        with pytest.raises(AppError):
            Project.open(path)
    with sqlite3.connect(path) as read:
        assert read.execute("SELECT value FROM schema_meta").fetchone()[0] == "3"
    reopened = Project.open(path)
    try:
        assert runs.fetch(reopened.connection, run) == original
        assert (
            reopened.connection.execute(
                "SELECT COUNT(*) FROM audio_assignments"
            ).fetchone()[0]
            == 0
        )
        assert path.with_name("project.schema-v3.sqlite.bak").exists()
    finally:
        reopened.close()


@pytest.mark.parametrize("assigned", [False, True])
def test_omitted_expectations_are_unknown_and_no_assignment_is_legacy(
    tmp_path: Path, assigned: bool
) -> None:
    source = generate("audio.digital_silence.001", tmp_path)
    services, asset = setup(tmp_path, source)
    services.jobs.detectors = (LevelDetector("audio.silence"),)
    params: dict[str, Any] = {
        "project_id": services.project.id if services.project else "",
        "media_asset_id": asset,
        "profile_key": "general_technical_qc",
        "profile_version": "1.2.0",
        "ai_mode": "OFF",
    }
    if assigned:
        params["audio_assignment"] = {
            "schema_version": "0.1.0",
            "source_sha256": digest(source),
            "provenance": "explicitly incomplete intent",
            "channels": [],
            "programs": [],
        }
    try:
        run = str(services.dispatch("analysis.start", params)["analysis_run_id"])
        result = finish(services, run)
        assert result["status"] == "COMPLETED", result
        assert result["overall_result"] == ("PASS" if assigned else "WARN")
        assert services.project
        rows = services.project.connection.execute("SELECT * FROM findings").fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["severity"] == ("INFO" if assigned else "WARN")
        measured = json.loads(row["measurements_json"])
        assert row["duration_seconds"] == pytest.approx(6, abs=1 / 48000)
        metadata = json.loads(row["metadata_json"])
        if assigned:
            assert metadata["applicability"] == "UNRESOLVED"
            assert measured["measurement_scope"]["members"] == [[0, 0]]
            assert "unknown" in str(result["interpretation_notes"])
        else:
            assert "applicability" not in metadata
            assert result["audio_assignment"] is None
    finally:
        services.close()


def test_explicit_mono_iso_program_does_not_use_default_mix(tmp_path: Path) -> None:
    source = generate("audio.production_multitrack.001", tmp_path)
    services, asset = setup(tmp_path, source)
    services.jobs.detectors = (LoudnessDetector("audio.loudness.integrated"),)
    doc = assignment(source)
    doc["programs"].append({"program_id": "lav", "layout": "mono", "members": [[0, 2]]})
    try:
        result = finish(services, start(services, asset, doc))
        assert result["status"] == "COMPLETED", result
        metrics = json.loads(result["detector_states"][0]["metrics_json"])
        programs = {
            p["measurement_scope"]["program_id"]: p
            for p in metrics["programs"].values()
        }
        assert programs["lav"]["measurement_scope"]["members"] == [[0, 2]]
        # Third channel amplitude is 0.01, mix legs 0.1 each: 20 dB plus
        # two-channel energy weighting. Quantized PCM needs 0.03 LU tolerance.
        assert programs["L/R"]["integrated_lufs"] - programs["lav"][
            "integrated_lufs"
        ] == pytest.approx(20 + 10 * np.log10(2), abs=0.03)
        assert len(metrics["streams"]) == 1
    finally:
        services.close()


def test_retry_after_reopen_rejects_middle_change_beyond_fast_fingerprint(
    tmp_path: Path,
) -> None:
    import os

    from mediaqc_engine.media.inspection import fingerprint

    seed = generate("audio.production_multitrack.001", tmp_path / "seed")
    source = tmp_path / "large-synthetic.wav"
    with wave.open(str(seed), "rb") as original, wave.open(str(source), "wb") as output:
        output.setparams(original.getparams())
        pcm = original.readframes(original.getnframes())
        for _ in range(3):
            output.writeframes(pcm)
    services, asset = setup(tmp_path, source)
    services.jobs.detectors = (LevelDetector("audio.silence"),)
    doc = assignment(source)
    try:
        run = start(services, asset, doc)
        result = finish(services, run)
        assert result["status"] == "COMPLETED", result
        assert services.project
        path = services.project.path
    finally:
        services.close()
    old_fingerprint = fingerprint(source)
    stamp = source.stat()
    # Deliberately mutate only a generated test fixture, never reference media.
    with source.open("r+b") as output:
        output.seek(stamp.st_size // 2)
        value = output.read(1)
        output.seek(stamp.st_size // 2)
        output.write(bytes([value[0] ^ 1]))
    os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert fingerprint(source) == old_fingerprint
    assert digest(source) != doc["source_sha256"]
    reopened = Projects(state_directory=tmp_path / "reopened-state")
    try:
        reopened.dispatch("project.open", {"project_file": str(path)})
        reopened.jobs.detectors = (LevelDetector("audio.silence"),)
        retry = str(
            reopened.dispatch("analysis.retry", {"analysis_run_id": run})[
                "analysis_run_id"
            ]
        )
        failed = finish(reopened, retry)
        assert failed["status"] == "FAILED"
        assert failed["error_code"] == "MEDIA_CHANGED"
        assert not failed["detector_states"]
        assert failed["audio_assignment"] == doc
        historical = reopened.dispatch("analysis.get", {"analysis_run_id": run})
        for key in (
            "status",
            "overall_result",
            "audio_assignment",
            "detector_states",
            "summary",
        ):
            assert historical[key] == result[key]
    finally:
        reopened.close()
