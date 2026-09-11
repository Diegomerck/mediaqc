"""Phase 3 orchestration fixtures contain no detector algorithms."""

import hashlib
import json
import subprocess
import threading
import time
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO
from unittest.mock import patch

import pytest

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.app.projects import Projects
from mediaqc_engine.db import runs
from mediaqc_engine.db.project import Project
from mediaqc_engine.detectors.contract import DetectorContext, DetectorResult
from mediaqc_engine.jobs.recovery import Journal
from mediaqc_engine.qc import profiles


class FixtureDetector:
    detector_id = "audio.clipping"
    detector_version = "0.0.0-test"

    def __init__(self, mode: str = "complete"):
        self.mode = mode
        self.entered = threading.Event()
        self.calls = 0

    def supports(self, context: DetectorContext) -> bool:
        return self.mode != "skip"

    def analyze(self, context: DetectorContext) -> DetectorResult:
        self.calls += 1
        self.entered.set()
        if self.mode == "fail":
            raise RuntimeError("Synthetic detector failure")
        if self.mode == "wait":
            assert context.cancellation.event.wait(5)
            context.cancellation.check()
        if self.mode == "ffmpeg":
            context.media_tools.run(
                "ffmpeg",
                [
                    "-v",
                    "error",
                    "-nostdin",
                    "-protocol_whitelist",
                    "file",
                    "-re",
                    "-stream_loop",
                    "-1",
                    "-i",
                    str(context.media_asset["absolute_path"]),
                    "-f",
                    "null",
                    "-",
                ],
            )
        return DetectorResult(metrics={"fixture_completed": True})


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
            "profile_version": "1.0.0",
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


def test_complete_progress_snapshot_and_sequential_runs(
    session: tuple[Projects, str, Path, list[tuple[str, dict[str, object]]]],
) -> None:
    services, asset, _, events = session
    detector = FixtureDetector()
    services.jobs.detectors = (detector,)
    first = start(services, asset)
    result = finished(services, first)
    assert result["status"] == "COMPLETED"
    assert result["overall_result"] == "PASS"
    assert result["ffmpeg_version"] and result["ffprobe_version"]
    snapshot = result["qc_profile_snapshot_json"]
    assert json.loads(str(snapshot)) == profiles.builtin()
    assert result["media_fingerprint_sha256"]
    assert result["started_at"] and result["completed_at"]
    progress = [data for name, data in events if name == "analysis.progress"]
    assert progress and all(
        0 <= float(str(data["overall_progress"])) <= 1 for data in progress
    )
    assert [data["status"] for name, data in events if name == "analysis.status"] == [
        "QUEUED",
        "INSPECTING",
        "ANALYZING",
        "COMPLETED",
    ]
    second = start(services, asset)
    assert second != first and finished(services, second)["status"] == "COMPLETED"
    assert (
        services.dispatch("analysis.get", {"analysis_run_id": first})[
            "qc_profile_snapshot_json"
        ]
        == snapshot
    )


def test_cancel_stops_scheduling_and_retry_preserves_snapshot(
    session: tuple[Projects, str, Path, list[tuple[str, dict[str, object]]]],
) -> None:
    services, asset, _, events = session
    waiting, later = FixtureDetector("wait"), FixtureDetector()
    later.detector_id = "audio.true_peak"
    services.jobs.detectors = (waiting, later)
    identifier = start(services, asset)
    assert waiting.entered.wait(5)
    with pytest.raises(AppError) as conflict:
        start(services, asset)
    assert conflict.value.code == "RUN_START_FAILED"
    with pytest.raises(AppError):
        services.dispatch("analysis.retry", {"analysis_run_id": identifier})
    services.dispatch("analysis.cancel", {"analysis_run_id": identifier})
    result = finished(services, identifier)
    assert result["status"] == "CANCELLED" and later.calls == 0
    assert [name for name, _ in events].count("analysis.cancelled") == 1
    executions = result["detector_states"]
    assert isinstance(executions, list) and all(
        item["status"] == "CANCELLED" for item in executions
    )
    with pytest.raises(AppError) as terminal:
        services.dispatch("analysis.cancel", {"analysis_run_id": identifier})
    assert terminal.value.code == "RUN_ALREADY_TERMINAL"
    services.jobs.detectors = (FixtureDetector(),)
    with patch(
        "mediaqc_engine.qc.profiles.get",
        side_effect=AssertionError("Retry must use snapshot"),
    ):
        retry = services.dispatch("analysis.retry", {"analysis_run_id": identifier})
    rerun = finished(services, str(retry["analysis_run_id"]))
    assert rerun["status"] == "COMPLETED"
    assert rerun["qc_profile_snapshot_json"] == result["qc_profile_snapshot_json"]
    assert (
        services.dispatch("analysis.get", {"analysis_run_id": identifier})["status"]
        == "CANCELLED"
    )


@pytest.mark.parametrize("shutdown", [False, True])
def test_real_ffmpeg_cancellation_and_shutdown_reap_children(
    session: tuple[Projects, str, Path, list[tuple[str, dict[str, object]]]],
    shutdown: bool,
) -> None:
    services, asset, _, events = session
    services.jobs.detectors = (FixtureDetector("ffmpeg"),)
    children: list[subprocess.Popen[bytes]] = []
    original = subprocess.Popen

    def record(
        args: list[str],
        *,
        stdin: int,
        stdout: BinaryIO,
        stderr: BinaryIO,
        shell: bool,
        creationflags: int,
    ) -> subprocess.Popen[bytes]:
        # Same constructor arguments, captured to observe exact owned process handles.
        child = original(
            args,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            shell=shell,
            creationflags=creationflags,
        )
        children.append(child)
        return child

    with patch("mediaqc_engine.media.tools.subprocess.Popen", side_effect=record):
        identifier = start(services, asset)
        deadline = time.monotonic() + 5
        while not any(
            isinstance(child.args, list) and "-stream_loop" in child.args
            for child in children
        ):
            assert time.monotonic() < deadline
            time.sleep(0.01)
        if shutdown:
            services.jobs.shutdown()
        else:
            services.dispatch("analysis.cancel", {"analysis_run_id": identifier})
        assert finished(services, identifier)["status"] == "CANCELLED"
    assert children and all(child.poll() is not None for child in children)
    assert services.jobs.tools is not None and services.jobs.tools.pids == []
    assert any(name == "analysis.cancelled" for name, _ in events)


@pytest.mark.parametrize("mode,status", [("fail", "FAILED"), ("skip", "COMPLETED")])
def test_detector_failure_isolation_and_supports(
    session: tuple[Projects, str, Path, list[tuple[str, dict[str, object]]]],
    mode: str,
    status: str,
) -> None:
    services, asset, _, _ = session
    first, second = FixtureDetector(mode), FixtureDetector()
    second.detector_id = "audio.true_peak"
    services.jobs.detectors = (first, second)
    result = finished(services, start(services, asset))
    assert result["status"] == status and second.calls == 1
    assert services.dispatch("project.get", {})["analysis_runs"]


def test_disabled_and_missing_detectors_never_fake_qc_pass(
    session: tuple[Projects, str, Path, list[tuple[str, dict[str, object]]]],
) -> None:
    services, asset, _, _ = session
    detector = FixtureDetector()
    detector.detector_id = (
        "audio.loudness.momentary"  # Disabled in the built-in profile.
    )
    services.jobs.detectors = (detector,)
    result = finished(services, start(services, asset))
    assert detector.calls == 0
    assert result["status"] == "FAILED" and result["overall_result"] is None
    assert result["error_code"] == "RUN_START_FAILED"


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"profile_key": "missing"}, "PROFILE_NOT_FOUND"),
        ({"ai_mode": "LOCAL"}, "INVALID_REQUEST"),
        ({"media_asset_id": "missing"}, "MEDIA_NOT_FOUND"),
        ({"extra": "x"}, "INVALID_REQUEST"),
    ],
)
def test_invalid_start_is_recoverable(
    session: tuple[Projects, str, Path, list[tuple[str, dict[str, object]]]],
    overrides: dict[str, object],
    code: str,
) -> None:
    services, asset, _, _ = session
    with pytest.raises(AppError) as failure:
        start(services, asset, **overrides)
    assert failure.value.code == code
    assert not services.jobs.active
    assert services.dispatch("project.get", {})["id"]


@pytest.mark.parametrize("state", sorted(runs.ACTIVE))
def test_startup_journal_recovers_each_nonterminal_state(
    tmp_path: Path, state: str
) -> None:
    project = Project.create(tmp_path / "project", "Recovery")
    asset = project.save_media(
        {
            "absolute_path": str(tmp_path / "source"),
            "file_name": "source",
            "file_size_bytes": 0,
            "inspection_status": "COMPLETED",
        },
        [],
    )
    identifier = runs.create(
        project.connection, project.id, asset, profiles.builtin(), "fingerprint"
    )
    with project.connection:
        project.connection.execute(
            "UPDATE analysis_runs SET status=? WHERE id=?", (state, identifier)
        )
        project.connection.execute(
            "INSERT INTO detector_executions (id,analysis_run_id,detector_id,"
            "detector_version,status) VALUES "
            "('execution',?,'audio.clipping','test','RUNNING')",
            (identifier,),
        )
    journal = Journal(tmp_path / "journal")
    journal.record(identifier, project.path)
    path = project.path
    project.close()
    recovered = Projects(state_directory=tmp_path / "journal")
    try:
        reopened = Project.open(path)
        try:
            result = runs.summary(reopened.connection, identifier)
            assert (
                result["status"] == "FAILED"
                and result["error_code"] == "ENGINE_INTERRUPTED"
            )
            executions = result["detector_states"]
            assert isinstance(executions, list) and executions[0]["status"] == "FAILED"
        finally:
            reopened.close()
    finally:
        recovered.close()


def test_invalid_transition_and_project_lease(
    session: tuple[Projects, str, Path, list[tuple[str, dict[str, object]]]],
) -> None:
    services, asset, _, _ = session
    assert services.project is not None
    identifier = runs.create(
        services.project.connection, services.project.id, asset, profiles.builtin(), "f"
    )
    with pytest.raises(AppError):
        runs.transition(services.project.connection, identifier, "GENERATING_REPORT")
    other = Projects()
    try:
        with pytest.raises(AppError, match="another engine"):
            other.dispatch("project.open", {"project_file": str(services.project.path)})
        assert runs.fetch(services.project.connection, identifier)["status"] == "QUEUED"
    finally:
        other.close()


def test_changed_source_fails_before_detector(
    session: tuple[Projects, str, Path, list[tuple[str, dict[str, object]]]],
) -> None:
    services, asset, _, _ = session
    detector = FixtureDetector()
    services.jobs.detectors = (detector,)
    with patch(
        "mediaqc_engine.jobs.manager.fingerprint",
        return_value={"fast_fingerprint_sha256": "changed"},
    ):
        result = finished(services, start(services, asset))
    assert result["error_code"] == "MEDIA_CHANGED" and detector.calls == 0


def test_profile_duration_is_not_a_ratio_and_invalid_profile_is_rejected() -> None:
    profile = profiles.builtin()
    profiles.validate(profile)  # The specified two-second silence duration is valid.
    audio = profile["audio"]
    assert isinstance(audio, dict)
    audio["silence"]["min_duration_seconds"] = -1
    with pytest.raises(AppError) as error:
        profiles.validate(profile)
    assert error.value.code == "PROFILE_INVALID"
