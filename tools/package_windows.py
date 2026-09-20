"""Assemble the existing Windows release into a relocatable, audited ZIP."""

import hashlib
import importlib.metadata
import json
import platform
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "apps/desktop/src-tauri/target/release"


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def inventory(directory: Path) -> list[dict[str, object]]:
    return [
        {
            "path": path.relative_to(directory).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": digest(path),
        }
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != "release-manifest.json"
    ]


def assemble(release: Path, destination: Path) -> Path:
    # Refuse merging with stale artifacts; callers choose a new output directory.
    required = [
        release / "mediaqc-desktop.exe",
        release / "resources/engine/mediaqc-engine.exe",
        release / "resources/engine/ffmpeg/ffmpeg.exe",
        release / "resources/engine/ffmpeg/ffprobe.exe",
        release / "resources/engine/ffmpeg/provenance.json",
        release / "resources/engine/ffmpeg/LICENSE",
        release / "resources/engine/_internal/python312.dll",
    ]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir(parents=True)
    shutil.copy2(required[0], destination / "MediaQC.exe")
    shutil.copytree(release / "resources", destination / "resources")
    shutil.copy2(ROOT / "docs/WINDOWS_RELEASE.md", destination / "README.md")
    notices = destination / "build-records"
    notices.mkdir()
    for name in ("uv.lock", "package-lock.json", "pyproject.toml"):
        shutil.copy2(ROOT / name, notices / name)
    shutil.copy2(ROOT / "apps/desktop/src-tauri/Cargo.lock", notices / "Cargo.lock")
    data = {
        "created_at": datetime.now(UTC).isoformat(),
        "application_version": json.loads((ROOT / "package.json").read_text())[
            "version"
        ],
        "architecture": platform.machine(),
        "python": sys.version,
        "python_dependencies": {
            name: importlib.metadata.version(name)
            for name in (
                "numpy",
                "scipy",
                "opencv-python-headless",
                "reportlab",
                "pillow",
                "charset-normalizer",
                "pyinstaller",
            )
        },
        "ffmpeg": json.loads(required[4].read_text()),
        "webview2": "Evergreen runtime required; not included in portable ZIP",
        "ai": "OFF; no production provider or model included",
        "signing": "Inspect Authenticode signatures; assembly does not sign files",
        "files": inventory(destination),
    }
    (destination / "release-manifest.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )
    archive = destination.with_suffix(".zip")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(destination.parent))
    archive.with_suffix(".zip.sha256").write_text(
        f"{digest(archive)}  {archive.name}\n", encoding="utf-8"
    )
    return archive


if __name__ == "__main__":
    output = (
        ROOT
        / "dist"
        / datetime.now(UTC).strftime("MediaQC-%Y%m%dT%H%M%SZ-portable-x64")
    )
    print(assemble(RELEASE, output))
