"""Release-bundled video QC through the production Windows controller, offline."""

import hashlib
import os
import subprocess
from pathlib import Path
from uuid import uuid4

from generate_test_media.video import generate

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    directory = ROOT / ".cache" / f"phase5 音楽 O'Brien & Sons {uuid4()}"
    for suffix in (".mp4", ".mxf"):
        smoke(directory / suffix[1:], suffix)


def smoke(directory: Path, suffix: str) -> None:
    source = generate("video.black.001", directory, suffix)
    before = hashlib.sha256(source.read_bytes()).hexdigest(), source.stat().st_mtime_ns
    result = subprocess.run(
        [
            str(ROOT / "apps/desktop/src-tauri/target/debug/examples/engine_smoke.exe"),
            "--video",
            str(directory / "project"),
            str(source),
        ],
        cwd=directory,
        env=dict(os.environ, PATH="", PYTHONPATH=""),
        capture_output=True,
        text=True,
        check=True,
        timeout=90,
    )
    print(result.stdout)
    assert "PASS: Phase 5" in result.stdout
    assert before == (
        hashlib.sha256(source.read_bytes()).hexdigest(),
        source.stat().st_mtime_ns,
    )
    print("PASS: Phase 5 source bytes and mtime unchanged; empty end-user PATH")


if __name__ == "__main__":
    main()
