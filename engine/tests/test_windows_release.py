"""Release prerequisites, relocation and bounded validation hashing regressions."""

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from package_windows import ROOT, assemble, digest, inventory
from windows_memory import sample


def make_release(root: Path) -> None:
    for name in (
        "mediaqc-desktop.exe",
        "resources/engine/mediaqc-engine.exe",
        "resources/engine/ffmpeg/ffmpeg.exe",
        "resources/engine/ffmpeg/ffprobe.exe",
        "resources/engine/ffmpeg/LICENSE",
        "resources/engine/_internal/python312.dll",
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    (root / "resources/engine/ffmpeg/provenance.json").write_text("{}")


def test_release_config_offline_per_user_without_fixed_runtime() -> None:
    config = json.loads(
        (ROOT / "apps/desktop/src-tauri/tauri.release.conf.json").read_text()
    )
    assert config["bundle"]["targets"] == ["nsis"]
    windows = config["bundle"]["windows"]
    assert windows["webviewInstallMode"]["type"] == "offlineInstaller"
    assert windows["nsis"]["installMode"] == "currentUser"
    assert windows["digestAlgorithm"] == "sha256"
    assert "certificateThumbprint" not in windows


def test_portable_preserves_layout_and_verifiable_manifest(tmp_path: Path) -> None:
    release = tmp_path / "release"
    make_release(release)
    destination = tmp_path / "portable 音楽 & space"
    archive = assemble(release, destination)
    manifest = json.loads((destination / "release-manifest.json").read_text())
    assert manifest["files"] == inventory(destination)
    assert "not included" in manifest["webview2"]
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(tmp_path / "relocated")
    extracted = tmp_path / "relocated" / destination.name
    assert (
        extracted / "resources/engine/_internal/python312.dll"
    ).read_bytes() == b"fixture"
    assert (extracted / "MediaQC.exe").read_bytes() == b"fixture"
    assert inventory(extracted) == manifest["files"]
    (extracted / "MediaQC.exe").write_bytes(b"tampered")
    assert inventory(extracted) != manifest["files"]
    assert archive.with_suffix(".zip.sha256").read_text().startswith(digest(archive))
    with pytest.raises(FileExistsError):
        assemble(release, destination)


def test_missing_runtime_fails_before_creating_artifact(tmp_path: Path) -> None:
    release = tmp_path / "release"
    make_release(release)
    (release / "resources/engine/ffmpeg/ffprobe.exe").unlink()
    destination = tmp_path / "portable"
    with pytest.raises(FileNotFoundError):
        assemble(release, destination)
    assert not destination.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process accounting")
def test_memory_sampler_includes_live_child() -> None:
    child = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.read()"],
        stdin=subprocess.PIPE,
    )
    try:
        working, private, owned = sample(os.getpid())
        assert child.pid in owned
        assert working > 0 and private > 0
    finally:
        assert child.stdin is not None
        child.stdin.close()
        child.wait(timeout=10)
