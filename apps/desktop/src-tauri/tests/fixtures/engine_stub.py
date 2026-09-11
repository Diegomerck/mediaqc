"""Fault injection child for native controller integration tests only."""

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from mediaqc_engine.ipc.server import handle_line, write_message

mode = sys.argv[1]
output = sys.stdout.buffer
if mode == "jobs":
    from mediaqc_engine.app.projects import Projects
    from mediaqc_engine.ipc.server import serve
    from mediaqc_engine.media.tools import MediaTools

    class SlowTools(MediaTools):
        @contextmanager
        def own(self, child: subprocess.Popen[bytes]) -> Iterator[None]:
            with super().own(child):
                if isinstance(child.args, list) and "-stream_loop" in child.args:
                    sys.stderr.write(f"owned-ffmpeg-pid:{child.pid}\n")
                    sys.stderr.flush()
                yield

        def probe(self, path: Path) -> dict[str, object]:
            self.run(
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
                    str(path),
                    "-f",
                    "null",
                    "-",
                ],
            )
            return super().probe(path)

    from mediaqc_engine.jobs.manager import EventSink

    def job_projects(*, emit: EventSink, state_directory: Path | None) -> Projects:
        services = Projects(emit=emit, state_directory=state_directory)
        services.jobs.tool_factory = SlowTools
        return services

    with patch("mediaqc_engine.ipc.server.Projects", side_effect=job_projects):
        serve(sys.stdin.buffer, output, Path(sys.argv[2]))
    sys.exit(0)
if mode == "exit_before_ready":
    sys.exit(7)
if mode == "silent":
    time.sleep(30)
if mode == "invalid_json":
    output.write(b"debug prose\n")
    output.flush()
    time.sleep(30)
if mode == "oversized":
    output.write(b"x" * (1024 * 1024 + 2))
    output.flush()
    time.sleep(30)
if mode == "partial":
    output.write(b'{"type":"event"}')
    output.flush()
    sys.exit(0)
write_message(
    output,
    {
        "type": "event",
        "protocol_version": "9.0" if mode == "bad_version" else "1.0",
        "event": "engine.ready",
        "data": {},
    },
)
for line in sys.stdin.buffer:
    request = json.loads(line)
    method = request["method"]
    if method == "media.inspect" and mode == "inspection_timeout":
        sys.stderr.write("inspection-active\n")
        sys.stderr.flush()
        time.sleep(30)
    if mode == "stderr":
        sys.stderr.write("diagnostic noise " * 10000 + "\n")
        sys.stderr.flush()
    if method == "system.ping":
        if mode in {"events", "bad_event"}:
            write_message(
                output,
                {
                    "type": "event",
                    "protocol_version": "1.0",
                    "event": "analysis.progress",
                    "data": {
                        "analysis_run_id": "bd3ab941-a2e2-4303-a1a6-032c45d428a2",
                        "overall_progress": 2.0 if mode == "bad_event" else 0.5,
                        "stage": "ANALYZING",
                    },
                },
            )
        if mode == "crash":
            os._exit(17)
        if mode == "ping_timeout":
            time.sleep(30)
    if method == "system.shutdown":
        if mode == "ignore_shutdown":
            time.sleep(30)
        if mode == "fail_shutdown":
            sys.exit(3)
    response, shutdown = handle_line(line)
    assert response is not None
    if method == "system.capabilities" and mode == "bad_capabilities":
        response["result"] = {"protocol_version": "2.0"}
    if method == "system.ping" and mode == "wrong_id":
        response["request_id"] = "00000000-0000-0000-0000-000000000000"
    write_message(output, response)
    if method == "system.ping" and mode == "events":
        write_message(
            output,
            {
                "type": "event",
                "protocol_version": "1.0",
                "event": "analysis.cancelled",
                "data": {
                    "analysis_run_id": "bd3ab941-a2e2-4303-a1a6-032c45d428a2",
                    "status": "CANCELLED",
                },
            },
        )
    if shutdown:
        break
