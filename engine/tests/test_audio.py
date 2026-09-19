"""Deterministic synthetic Phase 4 controls, defects, boundaries and IPC integration."""

import hashlib
import json
import logging
import threading
import wave
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import numpy as np
import pytest
from generate_test_media.audio import generate

from mediaqc_engine.app.errors import AppError
from mediaqc_engine.app.projects import Projects
from mediaqc_engine.db import findings, runs
from mediaqc_engine.db.project import Project
from mediaqc_engine.detectors.audio import registry
from mediaqc_engine.detectors.audio.common import settings
from mediaqc_engine.detectors.audio.dsp import Samples, correlation, db, rms, windows
from mediaqc_engine.detectors.contract import DetectorContext, DetectorResult
from mediaqc_engine.ipc.server import handle_line
from mediaqc_engine.jobs.cancellation import CancellationToken, Cancelled
from mediaqc_engine.media.tools import MediaTools
from mediaqc_engine.qc import profiles

RATE = 48000
MANIFEST = Path(__file__).resolve().parents[2] / "tests/fixtures/manifests/audio.json"


def tone(
    seconds: float = 4, amplitude: float = 0.1, frequency: float = 1000
) -> Samples:
    return (
        amplitude
        * np.sin(2 * np.pi * frequency * np.arange(round(seconds * RATE)) / RATE)
    )[:, None]


def write_audio(path: Path, samples: Samples) -> None:
    with wave.open(str(path), "wb") as output:
        output.setparams((samples.shape[1], 2, RATE, 0, "NONE", "not compressed"))
        output.writeframes(
            (np.clip(samples, -1, 32767 / 32768) * 32768).astype("<i2").tobytes()
        )


def context(tmp_path: Path, samples: Samples) -> DetectorContext:
    source = tmp_path / f"音楽 O'Brien & {uuid4()}.wav"
    write_audio(source, samples)
    token = CancellationToken()
    work = tmp_path / "cache" / str(uuid4())
    return DetectorContext(
        str(uuid4()),
        {"absolute_path": str(source), "duration_seconds": len(samples) / RATE},
        (
            {
                "id": str(uuid4()),
                "stream_type": "audio",
                "stream_index": 0,
                "sample_rate_hz": RATE,
                "channel_count": samples.shape[1],
                "duration_seconds": len(samples) / RATE,
            },
        ),
        profiles.builtin(),
        str(work),
        token,
        MediaTools(cancellation=token.event, cache=work),
        logging.LoggerAdapter(logging.getLogger(__name__), {}),
    )


def analyze(ctx: DetectorContext, name: str, **policy: object) -> DetectorResult:
    identifier = "audio." + name
    settings(ctx.qc_profile, identifier).update(policy)
    source = Path(str(ctx.media_asset["absolute_path"]))
    before = hashlib.sha256(source.read_bytes()).digest(), source.stat().st_mtime_ns
    detector = next(d for d in registry() if d.detector_id == identifier)
    try:
        result = detector.analyze(ctx)
        json.dumps(result.metrics, allow_nan=False)
        json.dumps(result.findings, allow_nan=False)
        return result
    finally:
        assert not ctx.media_tools.pids
        assert before == (
            hashlib.sha256(source.read_bytes()).digest(),
            source.stat().st_mtime_ns,
        )


def metrics(result: DetectorResult) -> dict[str, object]:
    streams = cast(dict[str, dict[str, object]], result.metrics["streams"])
    return next(iter(streams.values()))


def interval(
    result: DetectorResult, start: float, end: float, tolerance: float = 0.05
) -> None:
    assert result.findings
    finding = result.findings[0]
    assert float(str(finding["start_time_seconds"])) == pytest.approx(
        start, abs=tolerance
    )
    assert float(str(finding["end_time_seconds"])) == pytest.approx(end, abs=tolerance)
    assert float(str(finding["duration_seconds"])) == pytest.approx(
        end - start, abs=2 * tolerance
    )
    assert finding["detector_version"] == "1.0.0"
    assert finding["disposition"] == "OPEN"


def test_pure_math() -> None:
    assert db(0.1) == pytest.approx(-20)
    mono = tone(1)
    assert rms(mono) == pytest.approx(0.1 / np.sqrt(2), abs=1e-9)
    assert correlation(np.c_[mono, -mono], 0, 1) == pytest.approx(-1)
    assert correlation(np.zeros((100, 2)), 0, 1) is None


@pytest.mark.parametrize(
    "name", [d.detector_id.removeprefix("audio.") for d in registry()]
)
def test_clean_fixture_every_detector(tmp_path: Path, name: str) -> None:
    mono = tone(4, 0.1)
    ctx = context(tmp_path, np.c_[mono, mono])
    result = analyze(ctx, name)
    # 1 kHz stereo at -20 dBFS peak is approximately -20 LUFS, not the -23 target.
    if name == "loudness.integrated":
        result = analyze(ctx, name, target_lufs=-20.0, tolerance_lu=0.2)
    assert not result.findings, result.findings


def test_loudness_numeric_gating_and_cache(tmp_path: Path) -> None:
    ctx = context(tmp_path, tone(5))
    value = float(str(metrics(analyze(ctx, "loudness.integrated"))["integrated_lufs"]))
    assert value == pytest.approx(-23.0, abs=0.15)
    assert not analyze(
        ctx, "loudness.integrated", target_lufs=value + 1, tolerance_lu=1
    ).findings
    assert (
        analyze(
            ctx,
            "loudness.integrated",
            target_lufs=value + 1.01,
            tolerance_lu=1,
            severity="FAIL",
        ).findings[0]["severity"]
        == "FAIL"
    )
    with patch.object(
        ctx.media_tools,
        "stream",
        side_effect=AssertionError("must reuse R128 metadata"),
    ):
        assert metrics(analyze(ctx, "loudness.range"))[
            "loudness_range_lu"
        ] == pytest.approx(0, abs=0.1)
    quiet = context(
        tmp_path, np.r_[np.zeros((RATE * 3, 1)), tone(5), np.zeros((RATE * 3, 1))]
    )
    assert float(
        str(metrics(analyze(quiet, "loudness.integrated"))["integrated_lufs"])
    ) == pytest.approx(value, abs=0.4)


@pytest.mark.parametrize(
    "name,window", [("loudness.short_term", 3.0), ("loudness.momentary", 0.4)]
)
def test_windowed_loudness_bounds_and_short_media(
    tmp_path: Path, name: str, window: float
) -> None:
    ctx = context(tmp_path, tone(5))
    result = analyze(ctx, name, max_lufs=-25, min_event_duration_seconds=0.1)
    interval(result, window - 0.1, 5, 0.11)
    assert analyze(ctx, name, max_lufs=None, min_lufs=None).findings == []
    short = context(tmp_path, tone(0.2))
    assert metrics(analyze(short, name))["state"] == "INSUFFICIENT_DURATION"


def test_true_peak_intersample_and_sample_boundary(tmp_path: Path) -> None:
    wavelet = (
        1.1 * np.sin(2 * np.pi * 12000 * np.arange(RATE * 2) / RATE + np.pi / 4)
    )[:, None]
    ctx = context(tmp_path, wavelet)
    sample = metrics(analyze(ctx, "sample_peak"))["sample_peak_dbfs"]
    assert isinstance(sample, list)
    true = float(str(metrics(analyze(ctx, "true_peak"))["true_peak_dbtp"]))
    assert true > sample[0] + 2
    assert analyze(ctx, "true_peak").findings
    assert not analyze(ctx, "sample_peak", max_dbfs=sample[0]).findings
    assert analyze(ctx, "sample_peak", max_dbfs=sample[0] - 0.001).findings


@pytest.mark.parametrize("seconds", [0.001, 0.049, 0.099, 0.101, 0.199])
def test_true_peak_includes_short_files_and_final_partial_frame(
    tmp_path: Path, seconds: float
) -> None:
    data = np.zeros((round(RATE * seconds), 1))
    data[-2] = 0.95
    result = analyze(context(tmp_path, data), "true_peak")
    assert float(str(metrics(result)["true_peak_dbtp"])) > -0.6


def test_silent_integrated_loudness_is_not_a_fabricated_measurement(
    tmp_path: Path,
) -> None:
    result = analyze(context(tmp_path, np.zeros((RATE, 1))), "loudness.integrated")
    assert metrics(result)["integrated_lufs"] is None
    assert metrics(result)["state"] == "NO_GATED_AUDIO"


def test_clipping_cross_chunk_group_count_and_exact_minimum(tmp_path: Path) -> None:
    data = tone(2)
    data[RATE - 2 : RATE + 3] = 1
    data[RATE + 100 : RATE + 103] = -1
    ctx = context(tmp_path, data)
    result = analyze(ctx, "clipping")
    interval(result, (RATE - 2) / RATE, (RATE + 103) / RATE, 1 / RATE)
    measurements = cast(dict[str, object], result.findings[0]["measurements"])
    assert measurements["clipped_sample_count"] == 8
    assert measurements["max_consecutive_samples"] == 5
    assert not analyze(ctx, "clipping", min_consecutive_samples=6).findings
    assert (
        len(
            analyze(ctx, "clipping", merge_gap_ms=0, min_consecutive_samples=3).findings
        )
        == 2
    )


def test_silence_boundaries_edges_and_stereo(tmp_path: Path) -> None:
    data = tone(5)
    data[RATE : RATE * 3] = 0
    ctx = context(tmp_path, data)
    interval(analyze(ctx, "silence"), 1, 3)
    assert not analyze(ctx, "silence", min_duration_seconds=2.01).findings
    assert not analyze(
        ctx, "silence", min_duration_seconds=2, ignore_head_seconds=1.1
    ).findings
    active_right = context(tmp_path, np.c_[np.zeros(RATE * 4), tone(4)])
    assert not analyze(active_right, "silence").findings
    digital = context(tmp_path, np.zeros((RATE * 4, 1)))
    assert not analyze(digital, "silence", ignore_tail_seconds=1).findings


def test_pair_selection_mono_multichannel_and_phase(tmp_path: Path) -> None:
    mono = tone(3)
    ctx = context(tmp_path, np.c_[mono, mono, mono, -mono * 0.1])
    assert not analyze(ctx, "channel_imbalance").findings
    assert analyze(ctx, "channel_imbalance", pairs=[[2, 3]]).findings
    assert not analyze(ctx, "phase_correlation").findings
    interval(analyze(ctx, "phase_correlation", pairs=[[2, 3]]), 0, 3)
    assert not analyze(ctx, "phase_correlation", min_correlation=-1).findings
    mono_ctx = context(tmp_path, mono)
    for name in ("phase_correlation", "channel_imbalance"):
        assert metrics(analyze(mono_ctx, name))["state"] == "NOT_APPLICABLE"
    assert not analyze(
        context(tmp_path, np.zeros((RATE, 2))), "phase_correlation"
    ).findings


@pytest.mark.parametrize("fundamental", [50, 60])
def test_hum_families_and_persistence(tmp_path: Path, fundamental: int) -> None:
    hum = sum(
        (tone(4, 0.03 / harmonic, fundamental * harmonic) for harmonic in range(1, 6)),
        start=np.zeros((RATE * 4, 1)),
    )
    ctx = context(tmp_path, hum)
    result = analyze(ctx, "hum")
    interval(result, 0, 4, 0.5)
    values = cast(dict[str, object], result.findings[0]["measurements"])
    assert values["fundamental_hz"] == fundamental
    assert values["harmonics_detected"] == 5
    assert values["persistence_ratio"] == 1
    assert not analyze(ctx, "hum", min_hum_level_db_relative=1).findings
    transient = context(tmp_path, np.r_[tone(5), hum[:RATE], tone(5)])
    assert not analyze(transient, "hum", min_persistence_ratio=0.75).findings


def test_noise_quiet_spectral_gating_confidence_and_insufficiency(
    tmp_path: Path,
) -> None:
    noise = np.random.default_rng(42).normal(0, 0.01, (RATE * 5, 1))
    ctx = context(tmp_path, noise)
    result = analyze(ctx, "noise_floor", quiet_percentile=100)
    assert result.findings and result.findings[0]["confidence"] is not None
    assert metrics(result)["estimated_noise_floor_dbfs"] == pytest.approx(-40, abs=0.15)
    assert float(str(metrics(result)["quiet_audio_seconds"])) == pytest.approx(
        5, abs=0.1
    )
    assert not analyze(ctx, "noise_floor", max_estimated_noise_floor_dbfs=-39).findings
    for samples in (tone(5), noise[:1000], np.zeros((RATE * 5, 1)), noise * 30):
        result = analyze(context(tmp_path, samples), "noise_floor")
        assert metrics(result)["state"] == "INSUFFICIENT_QUIET_REGIONS"
        assert metrics(result)["estimated_noise_floor_dbfs"] is None
        assert result.warnings


@pytest.mark.parametrize(
    "milliseconds,expected",
    [(4, False), (5, True), (20, True), (250, True), (251, False), (1000, False)],
)
def test_dropout_duration_and_activity(
    tmp_path: Path, milliseconds: int, expected: bool
) -> None:
    data = tone(3)
    data[RATE : RATE + milliseconds * 48] = 0
    result = analyze(context(tmp_path, data), "dropout")
    assert bool(result.findings) is expected
    if expected:
        interval(result, 1, 1 + milliseconds / 1000, 0.002)
    assert not analyze(
        context(tmp_path, np.r_[np.zeros((RATE // 10, 1)), tone(1)]), "dropout"
    ).findings


def test_discontinuity_isolated_jump_and_sensitivity(tmp_path: Path) -> None:
    data = tone(3)
    data[RATE] = 0.9
    ctx = context(tmp_path, data)
    result = analyze(ctx, "discontinuity")
    interval(result, 1, 1, 0.001)
    assert result.findings[0]["severity"] == "WARN"
    assert result.findings[0]["confidence"] is not None
    assert not analyze(ctx, "discontinuity", min_jump_amplitude=1).findings


def test_single_channel_dropout_is_not_hidden_by_the_other_channel(
    tmp_path: Path,
) -> None:
    left = tone(3)
    right = left.copy()
    right[RATE : RATE + 960] = 0
    result = analyze(context(tmp_path, np.c_[left, right]), "dropout")
    interval(result, 1, 1.02, 0.002)
    assert len(result.findings) == 1
    assert cast(dict[str, object], result.findings[0]["measurements"])[
        "channel_indices"
    ] == [1]


def test_phase_injection_off_window_boundary_within_50ms(tmp_path: Path) -> None:
    left = tone(3)
    right = left.copy()
    right[round(1.038 * RATE) : round(1.638 * RATE)] *= -1
    result = analyze(context(tmp_path, np.c_[left, right]), "phase_correlation")
    interval(result, 1.038, 1.638, 0.05)


def test_stream_errors_cancellation_and_bounded_windows(tmp_path: Path) -> None:
    ctx = context(tmp_path, tone(4))
    assert max(len(block) for _, block, _ in windows(ctx, ctx.streams[0], 0.01)) <= 480
    ctx.cancellation.cancel()
    with pytest.raises(Cancelled):
        analyze(ctx, "clipping")
    broken = context(tmp_path, tone(1))
    Path(str(broken.media_asset["absolute_path"])).write_bytes(b"invalid audio")
    with pytest.raises(AppError) as error:
        analyze(broken, "sample_peak")
    assert error.value.code == "MEDIA_UNSUPPORTED"
    assert error.value.details["stderr_excerpt"]


def test_cancel_real_decode_during_window_callback(tmp_path: Path) -> None:
    ctx = context(tmp_path, tone(4))
    entered = threading.Event()

    def cancel(seconds: float) -> None:
        assert ctx.media_tools.pids
        entered.set()
        ctx.cancellation.cancel()
        ctx.media_tools.cancel()

    with pytest.raises(Cancelled):
        analyze(replace(ctx, report_progress=cancel), "silence")
    assert entered.is_set() and not ctx.media_tools.pids


@pytest.mark.parametrize(
    "name,patches",
    [
        ("phase_correlation", {"pairs": [[-1, 1]]}),
        ("phase_correlation", {"pairs": [[0, 0]]}),
        ("phase_correlation", {"pairs": [[True, 1]]}),
        ("phase_correlation", {"min_correlation": -2}),
        ("dropout", {"min_duration_ms": 300}),
        ("hum", {"fundamentals_hz": [0]}),
        ("hum", {"harmonics": 2.5}),
        ("clipping", {"merge_gap_ms": -1}),
        ("noise_floor", {"quiet_percentile": 101}),
        ("noise_floor", {"min_spectral_flatness": 2}),
        ("loudness.short_term", {"min_lufs": -10, "max_lufs": -20}),
        ("true_peak", {"max_dbtp": float("nan")}),
    ],
)
def test_invalid_audio_profiles(name: str, patches: dict[str, object]) -> None:
    profile = profiles.builtin()
    settings(profile, "audio." + name).update(patches)
    with pytest.raises(AppError) as error:
        profiles.validate(profile)
    assert error.value.code == "PROFILE_INVALID"


def test_production_persistence_ipc_reopen_and_immutability(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    samples = tone(3)
    samples[RATE : RATE + 200] = 1
    write_audio(source, samples)
    before = source.read_bytes(), source.stat().st_mtime_ns
    events: list[str] = []
    services = Projects(
        emit=lambda event, _: events.append(event), state_directory=tmp_path / "state"
    )
    try:
        project = services.dispatch(
            "project.create", {"name": "Audio", "directory": str(tmp_path / "project")}
        )
        asset = services.dispatch(
            "media.inspect", {"project_id": project["id"], "absolute_path": str(source)}
        )
        started = services.dispatch(
            "analysis.start",
            {
                "project_id": project["id"],
                "media_asset_id": asset["media_asset_id"],
                "profile_key": "general_technical_qc",
                "profile_version": "1.1.0",
                "ai_mode": "OFF",
            },
        )
        assert services.jobs.worker is not None
        services.jobs.worker.join(30)
        assert not services.jobs.active
        result = services.dispatch(
            "analysis.get", {"analysis_run_id": started["analysis_run_id"]}
        )
        assert result["status"] == "COMPLETED", result
        assert result["overall_result"] == "FAIL"
        assert "analysis.finding_created" in events and "analysis.completed" in events
        states = cast(list[dict[str, object]], result["detector_states"])
        assert (
            len([s for s in states if str(s["detector_id"]).startswith("audio.")]) == 13
        )
        assert (
            len(
                [
                    s
                    for s in states
                    if str(s["detector_id"]).startswith("video.")
                    and s["status"] == "SKIPPED"
                ]
            )
            == 13
        )
        request = {
            "type": "request",
            "protocol_version": "1.0",
            "request_id": str(uuid4()),
            "method": "finding.list",
            "params": {
                "analysis_run_id": started["analysis_run_id"],
                "detector_id": "audio.clipping",
            },
        }
        response, _ = handle_line(json.dumps(request).encode(), services)
        assert response is not None and response["ok"]
        listed = cast(dict[str, object], response["result"])
        finding = cast(list[dict[str, object]], listed["findings"])[0]
        detail = services.dispatch("finding.get", {"finding_id": finding["id"]})
        evidence = cast(list[dict[str, object]], detail["evidence"])[0]
        assert (tmp_path / "project" / str(evidence["relative_path"])).is_file()
        services.close()
        services = Projects(state_directory=tmp_path / "state")
        services.dispatch("project.open", {"project_file": project["project_file"]})
        assert (
            services.dispatch("finding.get", {"finding_id": finding["id"]})[
                "measurements"
            ]
            == finding["measurements"]
        )
        assert (
            services.dispatch(
                "analysis.get", {"analysis_run_id": started["analysis_run_id"]}
            )["overall_result"]
            == "FAIL"
        )
    finally:
        services.close()
    assert before == (source.read_bytes(), source.stat().st_mtime_ns)
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == ["source.wav"]


@pytest.mark.parametrize("fixture", json.loads(MANIFEST.read_text()))
def test_golden_manifest(tmp_path: Path, fixture: dict[str, object]) -> None:
    source = generate(str(fixture["fixture_id"]), tmp_path / "source")
    with wave.open(str(source), "rb") as audio:
        samples = (
            np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2")
            .astype(np.float64)
            .reshape(-1, audio.getnchannels())
            / 32768
        )
    ctx = context(tmp_path, samples)
    for expectation in cast(list[dict[str, object]], fixture["expected_findings"]):
        result = analyze(ctx, str(expectation["detector_id"]).removeprefix("audio."))
        assert result.findings
        assert result.findings[0]["severity"] == expectation["severity_min"]
        if "start_time_seconds" in expectation:
            interval(
                result,
                float(str(expectation["start_time_seconds"])),
                float(str(expectation["end_time_seconds"])),
                float(str(expectation["timestamp_tolerance_seconds"])),
            )
    for forbidden in cast(
        list[dict[str, object]], fixture.get("forbidden_findings", [])
    ):
        assert not analyze(
            ctx, str(forbidden["detector_id"]).removeprefix("audio.")
        ).findings


def test_multiple_stream_ids_offsets_and_profile_severity(tmp_path: Path) -> None:
    ctx = context(tmp_path, np.zeros((RATE * 3, 1)))
    second = {**ctx.streams[0], "id": "second-stream", "start_time_seconds": 2.0}
    result = analyze(
        replace(ctx, streams=(*ctx.streams, second)), "silence", severity="INFO"
    )
    assert len(result.findings) == 2
    assert result.findings[1]["stream_id"] == "second-stream"
    assert result.findings[1]["start_time_seconds"] == 2
    assert result.findings[1]["end_time_seconds"] == 5
    assert all(finding["severity"] == "INFO" for finding in result.findings)


def test_pcm_incomplete_and_nonfinite_rejected(tmp_path: Path) -> None:
    ctx = context(tmp_path, tone(1))
    for payload in (b"incomplete", np.array([np.nan], dtype="<f8").tobytes()):

        def chunks(
            arguments: list[str], block_bytes: int = 65536, data: bytes = payload
        ) -> Iterator[bytes]:
            yield data

        with (
            patch.object(ctx.media_tools, "stream", side_effect=chunks),
            pytest.raises(AppError),
        ):
            list(windows(ctx, ctx.streams[0], 0.1))


def test_lra_dynamic_programme_and_nullable_bounds(tmp_path: Path) -> None:
    ctx = context(tmp_path, np.r_[tone(10, 0.05), tone(10, 0.2)])
    result = analyze(ctx, "loudness.range")
    value = float(str(metrics(result)["loudness_range_lu"]))
    assert value == pytest.approx(12.04, abs=0.5)
    assert not analyze(ctx, "loudness.range", max_lu=value).findings
    assert analyze(ctx, "loudness.range", max_lu=value - 0.1).findings
    for detector, key in (
        ("true_peak", "max_dbtp"),
        ("sample_peak", "max_dbfs"),
        ("loudness.integrated", "target_lufs"),
        ("channel_imbalance", "max_difference_db"),
        ("phase_correlation", "min_correlation"),
        ("noise_floor", "max_estimated_noise_floor_dbfs"),
    ):
        settings(ctx.qc_profile, "audio." + detector)[key] = None
        profiles.validate(ctx.qc_profile)
        assert not analyze(ctx, detector).findings


def test_evidence_failure_preserves_finding_and_disposition_aggregation(
    tmp_path: Path,
) -> None:
    project = Project.create(tmp_path / "project", "Evidence")
    try:
        db = project.connection
        asset_id = str(uuid4())
        with db:
            db.execute(
                "INSERT INTO media_assets (id,project_id,absolute_path,file_name,"
                "file_size_bytes,inspection_status,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    asset_id,
                    project.id,
                    "source.wav",
                    "source.wav",
                    0,
                    "COMPLETED",
                    "2026-09-11T00:00:00Z",
                    "2026-09-11T00:00:00Z",
                ),
            )
        run_id = runs.create(
            db, project.id, asset_id, profiles.builtin(), "fingerprint"
        )
        execution_id = str(uuid4())
        with db:
            db.execute(
                "INSERT INTO detector_executions (id,analysis_run_id,detector_id,"
                "detector_version,status) VALUES (?,?,?,?,?)",
                (execution_id, run_id, "audio.silence", "1.0.0", "RUNNING"),
            )
        ctx = context(tmp_path, np.zeros((RATE * 3, 1)))
        draft = analyze(ctx, "silence").findings[0]
        draft["stream_id"] = None
        with (
            db,
            patch.object(Path, "write_text", side_effect=PermissionError("read only")),
        ):
            findings.save(db, project.path.parent, run_id, execution_id, draft)
        saved = findings.get(db, draft["id"])
        assert not saved["evidence"]
        assert cast(dict[str, object], saved["metadata"])["evidence_error"]
        assert findings.overall(db, run_id) == "WARN"
        with db:
            db.execute("UPDATE findings SET severity='FAIL' WHERE id=?", (draft["id"],))
        assert findings.overall(db, run_id) == "FAIL"
        for disposition in ("IGNORED", "FALSE_POSITIVE"):
            with db:
                db.execute(
                    "UPDATE findings SET disposition=? WHERE id=?",
                    (disposition, draft["id"]),
                )
            assert findings.overall(db, run_id) == "PASS"
    finally:
        project.close()
