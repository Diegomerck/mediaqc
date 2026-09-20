"""Build the pinned one-folder engine inside the repository (developer tooling)."""

import shutil
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
            "--collect-data",
            "mediaqc_engine",
            "--collect-data",
            "reportlab",
            "--copy-metadata",
            "numpy",
            "--copy-metadata",
            "scipy",
            "--copy-metadata",
            "opencv-python-headless",
            "--copy-metadata",
            "reportlab",
            "--copy-metadata",
            "pillow",
            "--copy-metadata",
            "charset-normalizer",
            "--hidden-import",
            "scipy.fft",
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
    source = ROOT / "engine/vendor/ffmpeg"
    if not (source / "provenance.json").is_file():
        raise RuntimeError("Run the developer media:prepare command before building")
    shutil.copytree(
        source, ROOT / "engine/dist/mediaqc-engine/ffmpeg", dirs_exist_ok=True
    )
    shutil.copy2(
        Path(sys.base_prefix) / "LICENSE.txt",
        ROOT / "engine/dist/mediaqc-engine/PYTHON-LICENSE.txt",
    )


if __name__ == "__main__":
    main()
