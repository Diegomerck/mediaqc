"""Release-bundled audio QC through the production Windows controller, offline."""

import hashlib
import os
import subprocess
from pathlib import Path
from uuid import uuid4

from generate_test_media.audio import generate

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    directory = ROOT / ".cache" / f"phase4 音楽 O'Brien & Sons {uuid4()}"
    source = generate("audio.clipping.001", directory)
    before = hashlib.sha256(source.read_bytes()).hexdigest(), source.stat().st_mtime_ns
    result = subprocess.run(
        [
            str(ROOT / "apps/desktop/src-tauri/target/debug/examples/engine_smoke.exe"),
            "--audio",
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
    assert "PASS: Phase 4" in result.stdout
    assert before == (
        hashlib.sha256(source.read_bytes()).hexdigest(),
        source.stat().st_mtime_ns,
    )
    print("PASS: Phase 4 source bytes and mtime unchanged; empty end-user PATH")


if __name__ == "__main__":
    main()
