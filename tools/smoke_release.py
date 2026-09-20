"""Run existing production-controller scenarios against extracted portable resources."""

import argparse
import json
import os
import subprocess
from pathlib import Path

from generate_test_media.audio import generate as audio
from generate_test_media.video import generate as video
from package_windows import ROOT, inventory
from validate_release import Client, fingerprint, validate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("distribution", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    distribution, output = args.distribution.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    before_resources = inventory(distribution)
    fixtures = output / "fixtures"
    sources = [
        ("--audio", audio("audio.clipping.001", fixtures)),
        ("--video", video("video.black.001", fixtures / "mp4")),
        ("--video", video("video.black.001", fixtures / "mxf", ".mxf")),
    ]
    harness = ROOT / "apps/desktop/src-tauri/target/debug/examples/engine_smoke.exe"
    for index, (mode, source) in enumerate(sources):
        before = fingerprint(source)
        result = subprocess.run(
            [str(harness), mode, str(output / f"project-{index}"), str(source)],
            cwd=output,
            env=dict(
                os.environ,
                PATH="",
                PYTHONPATH="",
                MEDIAQC_SMOKE_RESOURCES=str(distribution),
                MEDIAQC_SMOKE_LOGS=str(output / "logs"),
            ),
            capture_output=True,
            text=True,
            timeout=180,
        )
        (output / f"native-{index}.log").write_text(
            result.stdout + result.stderr, encoding="utf-8"
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert fingerprint(source) == before
    ffmpeg = distribution / "resources/engine/ffmpeg/ffmpeg.exe"
    mp3 = fixtures / "clean.mp3"
    subprocess.run(
        [
            str(ffmpeg),
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=997:sample_rate=48000:duration=6",
            "-ac",
            "2",
            str(mp3),
        ],
        check=True,
        timeout=30,
    )
    executable = distribution / "resources/engine/mediaqc-engine.exe"
    validate(executable, mp3, output / "mp3", False)
    bad = fixtures / "corrupt.mp4"
    bad.write_bytes(b"not a media container\0")
    before = fingerprint(bad)
    client = Client(executable, output)
    try:
        project = client.call(
            "project.create", directory=str(output / "bad-project"), name="Bad media"
        )
        rejected = False
        try:
            inspected = client.call(
                "media.inspect", project_id=project["id"], absolute_path=str(bad)
            )
            rejected = inspected["inspection_status"] != "COMPLETED"
        except RuntimeError as error:
            rejected = "MEDIA_" in str(error)
        assert rejected
        assert client.call("system.ping") == {"pong": True}
        assert fingerprint(bad) == before
    finally:
        client.close()
    assert inventory(distribution) == before_resources
    (output / "summary.json").write_text(
        json.dumps(
            {
                "WAV_MP4_MXF_production_controller": "PASS",
                "MP3_engine_QC_reports_reopen": "PASS",
                "corrupt_media_engine_survives": "PASS",
                "source_hash_size_mtime": "PASS",
                "resources_unchanged": "PASS",
                "PATH_PYTHONPATH": "empty",
                "firewall_offline": "UNVERIFIED",
                "clean_machine": "UNVERIFIED",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        "PASS: relocated release, WAV/MP3/MP4/MXF, corrupt media, "
        "resource/source immutability"
    )


if __name__ == "__main__":
    main()
