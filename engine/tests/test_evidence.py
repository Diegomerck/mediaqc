"""Phase 6 evidence/disposition contracts, real FFmpeg and immutable source fixtures."""

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import pytest
from generate_test_media.audio import generate as audio
from generate_test_media.video import generate as video

from mediaqc_engine import evidence
from mediaqc_engine.app.errors import AppError
from mediaqc_engine.app.projects import Projects
from mediaqc_engine.db import findings, runs
from mediaqc_engine.jobs.cancellation import CancellationToken, Cancelled
from mediaqc_engine.media.tools import MediaTools
from mediaqc_engine.qc import profiles


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


def test_visual_evidence_and_bounded_read(
    saved: tuple[Projects, str, str, Path],
) -> None:
    service, _, _, source = saved
    items = generate(saved)
    expected = (
        {"AUDIO_WAVEFORM", "AUDIO_SPECTROGRAM"}
        if source.suffix == ".wav"
        else {"VIDEO_FRAME_BEFORE", "VIDEO_FRAME", "VIDEO_FRAME_AFTER"}
    )
    assert {item["evidence_type"] for item in items} == expected | {"METRICS_JSON"}
    for item in items:
        result = service.dispatch("evidence.read", {"evidence_id": item["id"]})
        if item["evidence_type"] != "METRICS_JSON":
            assert str(result["data_url"]).startswith("data:image/png;base64,")
            assert len(str(result["data_url"])) < 350000
            assert (
                float(str(result["end_time_seconds"]))
                - float(str(result["start_time_seconds"]))
                <= 8
            )


@pytest.mark.parametrize(
    ("disposition", "overall"),
    [
        ("CONFIRMED", "FAIL"),
        ("FALSE_POSITIVE", "PASS"),
        ("IGNORED", "PASS"),
        ("OPEN", "FAIL"),
    ],
)
def test_dispositions_reopen_and_history(
    saved: tuple[Projects, str, str, Path], disposition: str, overall: str
) -> None:
    service, run, identifier, _ = saved
    assert service.project is not None
    project_file = str(service.project.path)
    runs.transition(service.project.connection, run, "COMPLETED")
    service.dispatch(
        "finding.set_disposition",
        {"finding_id": identifier, "disposition": disposition, "note": "Intentional é"},
    )
    service.close_project()
    service.dispatch("project.open", {"project_file": project_file})
    detail = service.dispatch("finding.get", {"finding_id": identifier})
    assert detail["disposition"] == disposition
    assert (
        cast(list[dict[str, object]], detail["feedback"])[0]["note"] == "Intentional é"
    )
    assert (
        service.dispatch("analysis.get", {"analysis_run_id": run})["overall_result"]
        == overall
    )
    assert detail["measurements"] == {"measured": 1}
    service.dispatch(
        "finding.set_disposition", {"finding_id": identifier, "disposition": "OPEN"}
    )
    assert (
        service.dispatch("analysis.get", {"analysis_run_id": run})["overall_result"]
        == "FAIL"
    )


def test_failed_generation_is_persisted(saved: tuple[Projects, str, str, Path]) -> None:
    service, run, identifier, _ = saved
    assert service.project is not None
    tools = MediaTools(cache=service.project.path.parent / "cache")
    with patch.object(
        tools,
        "run",
        side_effect=AppError(
            "MEDIA_UNSUPPORTED",
            "decode failed",
            {"stderr_excerpt": "fixture decoder error"},
        ),
    ):
        evidence.generate(
            service.project.connection,
            service.project.path.parent,
            run,
            tools,
            CancellationToken(),
        )
    detail = service.dispatch("finding.get", {"finding_id": identifier})
    errors = cast(
        list[dict[str, object]],
        cast(dict[str, object], detail["metadata"])["visual_evidence_errors"],
    )
    assert errors and all(item["code"] == "MEDIA_UNSUPPORTED" for item in errors)
    assert detail["measurements"] == {"measured": 1}


@pytest.mark.parametrize("mode", ["missing", "changed", "oversize", "escape"])
def test_artifact_failure_is_explicit(
    saved: tuple[Projects, str, str, Path], mode: str
) -> None:
    service, _, _, _ = saved
    item = generate(saved)[-1]
    assert service.project is not None
    path = service.project.path.parent / str(item["relative_path"])
    if mode == "missing":
        path.unlink()
    elif mode == "changed":
        path.write_bytes(b"changed")
    elif mode == "oversize":
        path.write_bytes(b"x" * (evidence.MAX_IMAGE_BYTES + 1))
    else:
        with service.project.connection:
            service.project.connection.execute(
                "UPDATE evidence SET relative_path=? WHERE id=?",
                ("../source.wav", item["id"]),
            )
    with pytest.raises(AppError, match="Evidence"):
        service.dispatch("evidence.read", {"evidence_id": item["id"]})


def test_changed_source_detected_without_writing_it(
    saved: tuple[Projects, str, str, Path],
) -> None:
    service, _, _, _ = saved
    item = generate(saved)[-1]
    with (
        patch(
            "mediaqc_engine.evidence.fingerprint",
            return_value={"fast_fingerprint_sha256": "changed"},
        ),
        pytest.raises(AppError) as error,
    ):
        service.dispatch("evidence.read", {"evidence_id": item["id"]})
    assert error.value.code == "EVIDENCE_STALE"


def test_cancel_evidence_reaps_real_child(
    saved: tuple[Projects, str, str, Path],
) -> None:
    service, run, _, source = saved
    assert service.project is not None
    token = CancellationToken()
    tools = MediaTools(
        cancellation=token.event, cache=service.project.path.parent / "cache"
    )
    token.cancel()
    with pytest.raises(Cancelled):
        evidence.generate(
            service.project.connection, service.project.path.parent, run, tools, token
        )
    assert not tools.pids
    assert source.exists()


def test_invalid_disposition_does_not_change_data(
    saved: tuple[Projects, str, str, Path],
) -> None:
    service, _, identifier, _ = saved
    with pytest.raises(AppError):
        service.dispatch(
            "finding.set_disposition",
            {"finding_id": identifier, "disposition": "DELETE"},
        )
    assert (
        service.dispatch("finding.get", {"finding_id": identifier})["disposition"]
        == "OPEN"
    )


def test_active_evidence_cancellation_owns_and_reaps_ffmpeg(
    saved: tuple[Projects, str, str, Path],
) -> None:
    import threading
    import time

    service, run, _, _ = saved
    assert service.project is not None
    token = CancellationToken()
    tools = MediaTools(
        cancellation=token.event, cache=service.project.path.parent / "cache"
    )
    real_run = tools.run
    seen = threading.Event()

    def cancel_child() -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if tools.pids:
                seen.set()
                token.cancel()
                tools.cancel()
                return
            token.event.wait(0.005)

    def slow_run(tool: str, arguments: list[str]) -> bytes:
        arguments = list(arguments)
        arguments[arguments.index("-i") : arguments.index("-i")] = ["-re"]
        return real_run(tool, arguments)

    watcher = threading.Thread(target=cancel_child)
    watcher.start()
    try:
        with patch.object(tools, "run", side_effect=slow_run), pytest.raises(Cancelled):
            evidence.generate(
                service.project.connection,
                service.project.path.parent,
                run,
                tools,
                token,
            )
    finally:
        tools.cancel()
        watcher.join(6)
    assert seen.is_set()
    assert not tools.pids


def test_disposition_precedence_keeps_active_warn(
    saved: tuple[Projects, str, str, Path],
) -> None:
    service, run, identifier, _ = saved
    assert service.project is not None
    db = service.project.connection
    draft = findings.get(db, identifier)
    draft.update(id=str(uuid4()), severity="WARN")
    with db:
        findings.save(
            db,
            service.project.path.parent,
            run,
            str(draft["detector_execution_id"]),
            draft,
        )
    runs.transition(db, run, "COMPLETED")
    service.dispatch(
        "finding.set_disposition", {"finding_id": identifier, "disposition": "IGNORED"}
    )
    assert (
        service.dispatch("analysis.get", {"analysis_run_id": run})["overall_result"]
        == "WARN"
    )
    service.dispatch(
        "finding.set_disposition",
        {"finding_id": draft["id"], "disposition": "CONFIRMED"},
    )
    assert (
        service.dispatch("analysis.get", {"analysis_run_id": run})["overall_result"]
        == "WARN"
    )
    service.dispatch(
        "finding.set_disposition",
        {"finding_id": draft["id"], "disposition": "FALSE_POSITIVE"},
    )
    assert (
        service.dispatch("analysis.get", {"analysis_run_id": run})["overall_result"]
        == "PASS"
    )


def test_stale_metrics_artifact_is_explicit(
    saved: tuple[Projects, str, str, Path],
) -> None:
    service, _, identifier, _ = saved
    assert service.project is not None
    detail = service.dispatch("finding.get", {"finding_id": identifier})
    item = cast(list[dict[str, object]], detail["evidence"])[0]
    path = service.project.path.parent / str(item["relative_path"])
    content = json.loads(path.read_text(encoding="utf-8"))
    content["measurements"] = {"measured": 100}
    path.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(AppError) as error:
        service.dispatch("evidence.read", {"evidence_id": item["id"]})
    assert error.value.code == "EVIDENCE_STALE"
