"""Relocated release IPC smoke and CPU benchmarks; never claims firewall validation."""

import argparse
import hashlib
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from windows_memory import sample


def fingerprint(path: Path) -> tuple[str, int, int]:
    with path.open("rb") as source:
        checksum = hashlib.file_digest(source, "sha256").hexdigest()
    return checksum, path.stat().st_size, path.stat().st_mtime_ns


class Client:
    def __init__(self, executable: Path, work: Path) -> None:
        self.messages: queue.Queue[dict[str, Any]] = queue.Queue()
        self.events: list[str] = []
        self.log = (work / "engine-stderr.log").open("wb")
        self.process = subprocess.Popen(
            [str(executable), "--state-directory", str(work / "state")],
            cwd=work,
            env=dict(os.environ, PATH="", PYTHONPATH="", PYTHONHOME=""),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log,
        )
        self.peak_ws = self.peak_private = 0
        self.samples = 0
        self.sampling_errors: list[str] = []
        self.done = threading.Event()
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.monitor = threading.Thread(target=self.measure, daemon=True)
        self.reader.start()
        self.monitor.start()
        assert self.messages.get(timeout=30)["event"] == "engine.ready"

    def read(self) -> None:
        assert self.process.stdout
        for line in self.process.stdout:
            self.messages.put(json.loads(line))

    def measure(self) -> None:
        while not self.done.is_set():
            try:
                working, private, _ = sample(self.process.pid)
                self.peak_ws = max(self.peak_ws, working)
                self.peak_private = max(self.peak_private, private)
                self.samples += 1
            except OSError as error:
                self.sampling_errors.append(str(error))
            self.done.wait(0.1)

    def call(self, method: str, **params: Any) -> dict[str, Any]:
        identifier = str(uuid4())
        assert self.process.stdin
        self.process.stdin.write(
            (
                json.dumps(
                    {
                        "type": "request",
                        "protocol_version": "1.0",
                        "request_id": identifier,
                        "method": method,
                        "params": params,
                    }
                )
                + "\n"
            ).encode()
        )
        self.process.stdin.flush()
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            message = self.messages.get(timeout=max(0.01, deadline - time.monotonic()))
            if message["type"] == "event":
                self.events.append(message["event"])
                continue
            assert message["request_id"] == identifier, message
            if not message["ok"]:
                raise RuntimeError(message)
            return cast(dict[str, Any], message["result"])
        raise TimeoutError(method)

    def wait_run(self, identifier: str) -> dict[str, Any]:
        deadline = time.monotonic() + 3600
        while time.monotonic() < deadline:
            result = self.call("analysis.get", analysis_run_id=identifier)
            if result["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                return result
            time.sleep(0.1)
        raise TimeoutError(identifier)

    def close(self) -> None:
        try:
            self.call("system.shutdown")
            assert self.process.wait(timeout=20) == 0
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=10)
            self.done.set()
            self.monitor.join(timeout=5)
            self.reader.join(timeout=5)
            self.log.close()


def validate(
    executable: Path, source: Path, work: Path, cancel: bool
) -> dict[str, Any]:
    work.mkdir(parents=True)
    before = fingerprint(source)
    client = Client(executable, work)
    try:
        capability = client.call("system.capabilities")
        assert capability["ai"]["local_available"] is False
        project = client.call(
            "project.create", directory=str(work / "project"), name="Release validation"
        )
        started = time.monotonic()
        inspected = client.call(
            "media.inspect", project_id=project["id"], absolute_path=str(source)
        )
        inspection_seconds = time.monotonic() - started
        started = time.monotonic()
        run = client.call(
            "analysis.start",
            project_id=project["id"],
            media_asset_id=inspected["media_asset_id"],
            profile_key="general_technical_qc",
            profile_version="1.2.0",
            ai_mode="OFF",
        )
        identifier = run["analysis_run_id"]
        if cancel:
            time.sleep(2)
            client.call("analysis.cancel", analysis_run_id=identifier)
        result = client.wait_run(identifier)
        elapsed = time.monotonic() - started
        assert result["status"] == ("CANCELLED" if cancel else "COMPLETED"), result
        if not cancel:
            assert all(
                item["status"] in {"COMPLETED", "SKIPPED"}
                for item in result["detector_states"]
            ), result
            for format_name in ("HTML", "PDF"):
                report = client.call(
                    "report.generate", analysis_run_id=identifier, format=format_name
                )
                assert Path(report["absolute_path"]).is_relative_to(work)
                assert Path(report["absolute_path"]).stat().st_size > 100
        else:
            assert "analysis.cancelled" in client.events
        assert client.call("system.ping") == {"pong": True}
        time.sleep(0.2)
        _, _, active = sample(client.process.pid)
        assert active == {client.process.pid}, (
            f"Owned children after terminal run: {active}"
        )
        summary = {
            "source": str(source),
            "source_bytes": before[1],
            "source_sha256": before[0],
            "source_mtime_ns": before[2],
            "inspection": inspected,
            "inspection_seconds": inspection_seconds,
            "analysis_seconds": elapsed,
            "status": result["status"],
            "profile": result["qc_profile_snapshot_json"],
            "detector_states": result["detector_states"],
            "ai": "OFF",
            "sampled_peak_tree_working_set_bytes": client.peak_ws,
            "sampled_peak_tree_private_bytes": client.peak_private,
            "memory_sample_count": client.samples,
            "memory_sample_interval_seconds": 0.1,
            "memory_sampling_errors": client.sampling_errors,
            "firewall_enforced": "UNVERIFIED",
            "developer_path": "empty",
            "source_unchanged": fingerprint(source) == before,
            "no_owned_children_after_terminal": True,
            "capabilities": capability,
            "project_file": project["project_file"],
        }
        assert summary["source_unchanged"]
        assert client.samples > 0 and not client.sampling_errors
    finally:
        client.close()
    # Reopen using a fresh process, not merely an existing in-memory connection.
    reopened = Client(executable, work)
    try:
        saved = reopened.call("project.open", project_file=summary["project_file"])
        assert any(item["id"] == identifier for item in saved["analysis_runs"])
        summary["reopen"] = "PASS"
    finally:
        reopened.close()
    (work / "result.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("distribution", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cancel", action="store_true")
    args = parser.parse_args()
    executable = args.distribution.resolve() / "resources/engine/mediaqc-engine.exe"
    result = validate(
        executable, args.source.resolve(), args.output.resolve(), args.cancel
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key
                not in {"profile", "capabilities", "inspection", "detector_states"}
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
