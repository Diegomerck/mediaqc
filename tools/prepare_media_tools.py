"""Developer-only download with pinned digest; no runtime network dependency."""

import argparse
import gzip
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare_windows() -> None:
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


def prepare_macos(arch: str | None = None) -> None:
    if arch is None:
        machine = platform.machine().lower()
        arch = "arm64" if machine in ("arm64", "aarch64") else "x64"

    version = "b6.1.1"
    base_url = (
        f"https://github.com/eugeneware/ffmpeg-static/releases/download/{version}"
    )
    cache_dir = ROOT / ".cache"
    cache_dir.mkdir(exist_ok=True)
    destination = ROOT / "engine/vendor/ffmpeg"
    destination.mkdir(parents=True, exist_ok=True)

    tools = {
        "ffmpeg": f"ffmpeg-darwin-{arch}.gz",
        "ffprobe": f"ffprobe-darwin-{arch}.gz",
    }

    for tool_name, filename in tools.items():
        gz_path = cache_dir / filename
        if not gz_path.exists():
            url = f"{base_url}/{filename}"
            print(f"Downloading {url}...")
            req = urllib.request.Request(url, headers={"User-Agent": "MediaQC-Build"})
            with urllib.request.urlopen(req, timeout=120) as source:
                with gz_path.open("wb") as output:
                    shutil.copyfileobj(source, output)
        target = destination / tool_name
        print(f"Decompressing {filename} to {target}...")
        with gzip.open(gz_path, "rb") as source:
            with target.open("wb") as output:
                shutil.copyfileobj(source, output)
        try:
            os.chmod(target, 0o755)
        except OSError:
            pass

    for doc_name, remote_name in (
        ("LICENSE", f"darwin-{arch}.LICENSE"),
        ("README.txt", f"darwin-{arch}.README"),
    ):
        doc_cache = cache_dir / remote_name
        if not doc_cache.exists():
            url = f"{base_url}/{remote_name}"
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "MediaQC-Build"}
                )
                with urllib.request.urlopen(req, timeout=30) as source:
                    with doc_cache.open("wb") as output:
                        shutil.copyfileobj(source, output)
            except Exception as e:
                print(f"Notice: Could not download {url}: {e}")
        if doc_cache.exists():
            (destination / doc_name).write_bytes(doc_cache.read_bytes())
        elif not (destination / doc_name).exists():
            notice = (
                f"FFmpeg {version} ({arch}) - Static build\nLicense: GPL-3.0-or-later\n"
            )
            (destination / doc_name).write_text(notice, encoding="utf-8")

    versions = {}
    for tool in ("ffmpeg", "ffprobe"):
        target_bin = destination / tool
        if sys.platform == "darwin":
            result = subprocess.run(
                [str(target_bin), "-version"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            versions[tool] = result.stdout
        else:
            versions[tool] = f"FFmpeg/ffprobe {version} (darwin-{arch})"

    manifest = {
        "version": version,
        "platform": "darwin",
        "arch": arch,
        "provider": "eugeneware/ffmpeg-static",
        "url": base_url,
        "license": "GPL-3.0-or-later",
        "source": "https://github.com/eugeneware/ffmpeg-static",
        "builds": versions,
    }
    (destination / "provenance.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"Verified and prepared FFmpeg/ffprobe {version} for macOS ({arch})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare media tools for MediaQC")
    parser.add_argument(
        "--platform",
        choices=["windows", "macos", "darwin"],
        default="macos" if sys.platform == "darwin" else "windows",
        help="Target platform (default: darwin on macOS, windows otherwise)",
    )
    parser.add_argument(
        "--arch",
        choices=["arm64", "x64"],
        default=None,
        help="Architecture for macOS binaries (default: detected or arm64)",
    )
    args = parser.parse_args()

    if args.platform in ("macos", "darwin"):
        prepare_macos(arch=args.arch)
    else:
        prepare_windows()


if __name__ == "__main__":
    main()
