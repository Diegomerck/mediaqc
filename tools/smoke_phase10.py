"""Validate Phase 10 against relocated packaged resources, without developer PATH."""

import argparse
import json
import os
import sqlite3
import subprocess
import time
import wave
from pathlib import Path
from typing import Any

from generate_test_media.video import generate
from package_windows import inventory
from validate_release import Client, fingerprint
from windows_memory import sample


def wait_batch(client: Client, identifier: str, states: set[str]) -> dict[str, Any]:
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        value = client.call("batch.get", batch_id=identifier)
        assert value["counts"]["processing"] <= 1, value
        if value["status"] in states:
            return value
        assert value["status"] not in {"FAILED", "STOPPED", "COMPLETED"}, value
        time.sleep(0.1)
    raise TimeoutError(identifier)


def active(client: Client, identifier: str, completed: int = 0) -> dict[str, Any]:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        value = client.call("batch.get", batch_id=identifier)
        if value["counts"]["processing"] and value["counts"]["processed"] >= completed:
            return value
        assert value["status"] == "RUNNING", value
        time.sleep(0.03)
    raise TimeoutError(identifier)


def create(client: Client, project: str, source: Path) -> str:
    value = client.call(
        "batch.create",
        project_id=project,
        name=source.name,
        source_kind="FOLDER",
        absolute_path=str(source),
    )
    identifier = str(value["batch_id"])
    wait_batch(client, identifier, {"READY"})
    return identifier


def start(client: Client, identifier: str, mode: str = "OFF") -> None:
    client.call(
        "batch.start",
        batch_id=identifier,
        profile_key="general_technical_qc",
        profile_version="1.2.0",
        ai_mode=mode,
    )


def wav(path: Path, seconds: int = 1) -> None:
    with wave.open(str(path), "wb") as target:
        target.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        for _ in range(seconds):
            target.writeframes(b"\0" * 96000)


def kill_owned_tree(client: Client) -> None:
    subprocess.run(
        [
            str(Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"),
            "/PID",
            str(client.process.pid),
            "/T",
            "/F",
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    client.process.wait(timeout=20)
    client.done.set()
    client.monitor.join(timeout=5)
    client.reader.join(timeout=5)
    client.log.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("distribution", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    distribution, output = args.distribution.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    resources = inventory(distribution)
    manifest = json.loads((distribution / "release-manifest.json").read_text())
    assert manifest["files"] == resources
    source = output / "sources"
    source.mkdir()
    for index in range(134):
        wav(source / f"{index:03}.wav")
    ffmpeg = distribution / "resources/engine/ffmpeg/ffmpeg.exe"
    subprocess.run(
        [
            str(ffmpeg),
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(source / "000.wav"),
            str(source / "audio.mp3"),
        ],
        check=True,
        timeout=30,
    )
    generate("video.clean.001", source, ".mp4")
    generate("video.clean.001", source, ".mxf")
    (source / "corrupt.mp4").write_bytes(b"invalid media")
    (source / "unsupported.flac").write_bytes(b"excluded")
    (source / "notes.txt").write_text("excluded")
    control = source / "controls"
    control.mkdir()
    for index in range(3):
        wav(control / f"{index}.wav", 30)
    before = {
        str(p.relative_to(source)): fingerprint(p)
        for p in source.rglob("*")
        if p.is_file()
    }
    executable = distribution / "resources/engine/mediaqc-engine.exe"
    client = Client(executable, output)
    record: dict[str, Any] = {
        "developer_PATH": "empty",
        "firewall_enforced": "UNVERIFIED",
    }
    try:
        capabilities = client.call("system.capabilities")
        assert capabilities["schema_version"] == 4
        assert capabilities["batch"]["max_active_files"] == 1
        assert capabilities["ai"]["local_available"] is False
        record["capabilities"] = capabilities
        project = client.call(
            "project.create",
            directory=str(output / "project"),
            name="Packaged batch",
            summary_mode="compact",
        )
        assert "media_assets" not in project
        inspected = client.call(
            "media.inspect",
            project_id=project["id"],
            absolute_path=str(control / "0.wav"),
        )
        run = client.call(
            "analysis.start",
            project_id=project["id"],
            media_asset_id=inspected["media_asset_id"],
            profile_key="general_technical_qc",
            profile_version="1.2.0",
            ai_mode="LOCAL",
        )
        saved = client.wait_run(run["analysis_run_id"])
        assert saved["status"] == "COMPLETED", saved
        with sqlite3.connect(project["project_file"]) as db:
            assert (
                db.execute(
                    "SELECT COUNT(*) FROM ai_reviews a JOIN findings f "
                    "ON f.id=a.finding_id "
                    "WHERE f.analysis_run_id=? AND a.status='UNAVAILABLE'",
                    (run["analysis_run_id"],),
                ).fetchone()[0]
                > 0
            )
        for kind in ("HTML", "PDF"):
            client.call(
                "report.generate", analysis_run_id=run["analysis_run_id"], format=kind
            )
        record["unavailable_LOCAL_QC_reports"] = "PASS"
        client.close()
        # A controlled schema-2 fixture retains real QC history and report records.
        with sqlite3.connect(project["project_file"]) as db:
            for table in (
                "audio_assignment_members",
                "audio_assignment_programs",
                "audio_assignment_channels",
                "audio_assignments",
                "batch_reports",
                "batch_items",
                "batches",
            ):
                db.execute(f"DROP TABLE {table}")
            db.execute("UPDATE schema_meta SET value='2' WHERE key='schema_version'")
        client = Client(executable, output)
        client.call(
            "project.open", project_file=project["project_file"], summary_mode="compact"
        )
        assert (
            Path(project["project_file"])
            .with_name("project.schema-v2.sqlite.bak")
            .is_file()
        )
        assert (
            client.call("analysis.get", analysis_run_id=run["analysis_run_id"])[
                "status"
            ]
            == "COMPLETED"
        )
        record["schema2_migration_history"] = "PASS"
        identifier = create(client, project["id"], source)
        snapshot = client.call("batch.get", batch_id=identifier)
        assert (
            snapshot["counts"]["total"] == 138
            and snapshot["import_summary"]["excluded"] == 2
        )
        with sqlite3.connect(project["project_file"]) as db:
            assert db.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0] == 1
        start(client, identifier)
        active(client, identifier)
        pause = client.call("batch.pause", batch_id=identifier)
        assert pause["status"] in {"PAUSING", "PAUSED"}
        paused = wait_batch(client, identifier, {"PAUSED"})
        assert paused["counts"]["processed"] >= 1 and paused["counts"]["pending"] > 0
        client.call("batch.resume", batch_id=identifier)
        samples = []
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            value = client.call("batch.get", batch_id=identifier)
            assert value["counts"]["processing"] <= 1
            with sqlite3.connect(project["project_file"]) as db:
                assert (
                    db.execute(
                        "SELECT COUNT(*) FROM analysis_runs WHERE status NOT IN "
                        "('COMPLETED','FAILED','CANCELLED')"
                    ).fetchone()[0]
                    <= 1
                )
            if value["status"] == "COMPLETED":
                break
            assert value["status"] == "RUNNING", value
            working, private, _ = sample(client.process.pid)
            samples.append(
                {
                    "processed": value["counts"]["processed"],
                    "working_set": working,
                    "private_bytes": private,
                }
            )
            time.sleep(0.25)
        else:
            raise TimeoutError("138-item packaged queue")
        assert value["counts"]["error"] == 1 and value["counts"]["processed"] == 138
        assert sum(value["counts"][key] for key in ("pass", "warn", "fail")) == 137
        for offset, length in ((0, 50), (50, 50), (100, 38)):
            page = client.call("batch.items", batch_id=identifier, offset=offset)
            assert page["total"] == 138 and len(page["items"]) == length
        assert (
            client.call("batch.items", batch_id=identifier, filter="ERROR")["total"]
            == 1
        )
        for kind in ("HTML", "PDF"):
            report = client.call(
                "batch.report.generate", batch_id=identifier, format=kind
            )
            assert Path(report["absolute_path"]).stat().st_size > 100
        record["batch_counts"] = value["counts"]
        record["batch_memory_samples"] = samples
        record["pause_resume_pagination_reports"] = "PASS"
        stopped = create(client, project["id"], control)
        start(client, stopped)
        active(client, stopped)
        client.call("batch.stop", batch_id=stopped)
        assert wait_batch(client, stopped, {"STOPPED"})["counts"]["cancelled"] > 0
        time.sleep(0.2)
        assert sample(client.process.pid)[2] == {client.process.pid}
        retry = client.call(
            "batch.retry", batch_id=stopped, selection="ALL_UNSUCCESSFUL"
        )["batch_id"]
        wait_batch(client, retry, {"READY"})
        start(client, retry)
        active(client, retry, completed=1)
        kill_owned_tree(client)
        client = Client(executable, output)
        client.call(
            "project.open", project_file=project["project_file"], summary_mode="compact"
        )
        recovered = client.call("batch.get", batch_id=retry)
        assert (
            recovered["status"] == "INTERRUPTED" and recovered["can_continue_pending"]
        )
        assert recovered["counts"]["processed"] >= 1
        client.call("batch.resume", batch_id=retry)
        wait_batch(client, retry, {"COMPLETED"})
        assert (
            client.call("batch.get", batch_id=identifier)["counts"]
            == record["batch_counts"]
        )
        record["stop_retry_crash_reopen_explicit_continue"] = "PASS"
        assert not client.sampling_errors, client.sampling_errors
    finally:
        if client.process.poll() is None:
            client.close()
    assert {
        str(p.relative_to(source)): fingerprint(p)
        for p in source.rglob("*")
        if p.is_file()
    } == before
    assert inventory(distribution) == resources
    record.update(
        source_immutability="PASS", resource_immutability="PASS", result="PASS"
    )
    (output / "phase10-summary.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8"
    )
    print("Phase 10 packaged smoke: PASS", flush=True)


if __name__ == "__main__":
    main()
