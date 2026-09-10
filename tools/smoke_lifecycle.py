"""Windows parent-death smoke test using the production Rust controller."""

import ctypes
import json
import queue
import subprocess
import threading
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "apps/desktop/src-tauri/target/debug/examples/engine_smoke.exe"


def main() -> None:
    result = subprocess.run(
        [str(HARNESS)], capture_output=True, text=True, timeout=30, check=True
    )
    print(result.stdout)
    assert 'ping: {"pong":true}' in result.stdout
    assert 'shutdown: {"forced":false}' in result.stdout
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    messages: queue.Queue[str] = queue.Queue()
    with subprocess.Popen(
        [str(HARNESS), "--hold"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as parent:
        assert parent.stdout is not None
        source = parent.stdout

        def read_output() -> None:
            for line in source:
                messages.put(line)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        handle = None
        try:
            pid = None
            for _ in range(3):
                line = messages.get(timeout=15)
                print(line.rstrip())
                if line.startswith("pid: "):
                    pid = int(line.removeprefix("pid: "))
            assert pid is not None
            # SYNCHRONIZE: observe this exact process handle, avoiding PID-reuse races.
            handle = kernel.OpenProcess(0x00100000, False, pid)
            assert handle, ctypes.get_last_error()
            parent.kill()
            parent.wait(timeout=5)
            assert kernel.WaitForSingleObject(handle, 5000) == 0, (
                "Owned engine survived parent death"
            )
            print(json.dumps({"parent_death_cleanup": "PASS", "engine_pid": pid}))
        finally:
            if parent.poll() is None:
                parent.kill()
                parent.wait(timeout=5)
            if handle:
                kernel.CloseHandle(handle)
            reader.join(timeout=5)


if __name__ == "__main__":
    main()
