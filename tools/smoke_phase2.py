"""Packaged Windows controller + engine + ffprobe + persistence smoke test."""

import hashlib
import os
import subprocess
import wave
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    directory = ROOT / ".cache" / f"phase2 音楽 O'Brien & Sons {uuid4()}"
    directory.mkdir(parents=True)
    source = directory / "source.wav"
    with wave.open(str(source), "wb") as output:
        output.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
        output.writeframes(b"\0" * 192000)
    original = (
        hashlib.sha256(source.read_bytes()).hexdigest(),
        source.stat().st_mtime_ns,
    )
    harness = ROOT / "apps/desktop/src-tauri/target/debug/examples/engine_smoke.exe"
    result = subprocess.run(
        [str(harness), "--inspect", str(directory / "project"), str(source)],
        cwd=directory,
        env=dict(os.environ, PATH="", PYTHONPATH=""),
        capture_output=True,
        text=True,
        check=True,
        timeout=45,
    )
    print(result.stdout)
    assert "PASS: Phase 2" in result.stdout
    assert (
        hashlib.sha256(source.read_bytes()).hexdigest(),
        source.stat().st_mtime_ns,
    ) == original
    print("PASS: packaged inspection with empty PATH and unchanged source bytes/mtime")


if __name__ == "__main__":
    main()
