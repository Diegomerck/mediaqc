"""Build the pinned one-folder engine inside the repository (developer tooling)."""

import os
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
    dest_license = ROOT / "engine/dist/mediaqc-engine/PYTHON-LICENSE.txt"
    for base in (Path(sys.base_prefix), Path(sys.prefix)):
        for name in ("LICENSE.txt", "LICENSE"):
            lic = base / name
            if lic.is_file():
                shutil.copy2(lic, dest_license)
                break
        if dest_license.is_file():
            break

    # On macOS/Unix, ensure the output binary has executable permissions (0o755).
    if sys.platform != "win32":
        output_binary = ROOT / "engine/dist/mediaqc-engine/mediaqc-engine"
        if output_binary.is_file():
            try:
                os.chmod(output_binary, 0o755)
            except OSError:
                pass
        dist_ffmpeg = ROOT / "engine/dist/mediaqc-engine/ffmpeg"
        if dist_ffmpeg.is_dir():
            for tool in ("ffmpeg", "ffprobe"):
                tool_path = dist_ffmpeg / tool
                if tool_path.is_file():
                    try:
                        os.chmod(tool_path, 0o755)
                    except OSError:
                        pass


if __name__ == "__main__":
    main()
