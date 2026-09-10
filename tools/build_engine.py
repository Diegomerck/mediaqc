"""Build the pinned one-folder engine inside the repository (developer tooling)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--onedir",
            "--console",
            "--name",
            "mediaqc-engine",
            "--distpath",
            str(ROOT / "engine/dist"),
            "--workpath",
            str(ROOT / ".cache/pyinstaller/work"),
            "--specpath",
            str(ROOT / ".cache/pyinstaller"),
            "--paths",
            str(ROOT / "engine/src"),
            str(ROOT / "engine/entrypoint.py"),
        ],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
