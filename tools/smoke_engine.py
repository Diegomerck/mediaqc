"""Exercise the standalone runtime with real sequential stdin/stdout requests."""

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def smoke(executable: Path) -> None:
    # An unrelated, Unicode working directory guards against shell/PATH assumptions.
    directory = ROOT / ".cache" / "smoke 音楽 O'Brien & Sons"
    directory.mkdir(parents=True, exist_ok=True)
    runtime = directory / "standalone runtime"
    shutil.copytree(executable.resolve().parent, runtime, dirs_exist_ok=True)
    executable = runtime / executable.name
    environment = dict(os.environ, PATH="", PYTHONPATH="")
    messages: queue.Queue[bytes] = queue.Queue()
    with subprocess.Popen(
        [str(executable.resolve())],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=directory,
        env=environment,
    ) as process:
        assert process.stdin and process.stdout and process.stderr
        source = process.stdout

        def read_output() -> None:
            for item in source:
                messages.put(item)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        try:
            ready = json.loads(messages.get(timeout=10))
            assert ready == {
                "type": "event",
                "protocol_version": "1.0",
                "event": "engine.ready",
                "data": {},
            }
            print(json.dumps(ready))
            for index, method in enumerate(
                ["system.capabilities"] + ["system.ping"] * 10000 + ["system.shutdown"]
            ):
                request_id = str(uuid4())
                process.stdin.write(
                    json.dumps(
                        {
                            "type": "request",
                            "protocol_version": "1.0",
                            "request_id": request_id,
                            "method": method,
                            "params": {},
                        }
                    ).encode()
                    + b"\n"
                )
                process.stdin.flush()
                raw = messages.get(timeout=10)
                assert raw.endswith(b"\n") and b"\r\n" not in raw
                response = json.loads(raw)
                assert set(response) == {
                    "type",
                    "protocol_version",
                    "request_id",
                    "ok",
                    "result",
                }
                assert (
                    response["type"] == "response"
                    and response["protocol_version"] == "1.0"
                )
                assert response["request_id"] == request_id and response["ok"] is True
                if method == "system.ping":
                    assert response["result"] == {"pong": True}
                if method == "system.capabilities":
                    assert response["result"]["ai"]["local_available"] is False
                    assert response["result"]["ai"]["provider"] is None
                    assert response["result"]["schema_version"] == 4
                if index in (0, 1, 10001):
                    print(json.dumps(response))
            assert process.wait(timeout=5) == 0
            assert process.stderr.read() == b""
            reader.join(timeout=5)
            print(
                "PASS: standalone runtime, 10,000 sequential pings, "
                "clean shutdown, empty PATH"
            )
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    smoke(
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "engine/dist/mediaqc-engine/mediaqc-engine.exe"
    )
