"""Developer-only download with pinned digest; no runtime network dependency."""

import hashlib
import json
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    manifest = json.loads((ROOT / "config/media-tools.json").read_text())
    archive = ROOT / ".cache" / f"ffmpeg-{manifest['version']}.zip"
    archive.parent.mkdir(exist_ok=True)
    if not archive.exists():
        with urllib.request.urlopen(manifest["url"], timeout=60) as source:
            with archive.open("wb") as output:
                shutil.copyfileobj(source, output)
    with archive.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != manifest["sha256"]:
        raise RuntimeError(
            "FFmpeg archive digest mismatch; remove the invalid cached archive"
        )
    destination = ROOT / "engine/vendor/ffmpeg"
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for name in ("ffmpeg.exe", "ffprobe.exe", "LICENSE", "README.txt"):
            candidates = [item for item in bundle.namelist() if Path(item).name == name]
            if len(candidates) != 1:
                raise RuntimeError(f"Expected exactly one {name} in pinned archive")
            (destination / name).write_bytes(bundle.read(candidates[0]))
    versions = {}
    for tool in ("ffmpeg", "ffprobe"):
        result = subprocess.run(
            [str(destination / f"{tool}.exe"), "-version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        versions[tool] = result.stdout
    (destination / "provenance.json").write_text(
        json.dumps({**manifest, "builds": versions}, indent=2), encoding="utf-8"
    )
    print(f"Verified and prepared FFmpeg/ffprobe {manifest['version']}")


if __name__ == "__main__":
    main()
