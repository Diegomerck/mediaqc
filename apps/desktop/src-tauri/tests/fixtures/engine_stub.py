"""Fault injection child for native controller integration tests only."""

import json
import os
import sys
import time

from mediaqc_engine.ipc.server import handle_line, write_message

mode = sys.argv[1]
output = sys.stdout.buffer
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
    if shutdown:
        break
