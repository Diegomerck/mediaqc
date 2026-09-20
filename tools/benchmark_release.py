"""Generate modest CPU fixtures and a sparse RF64 file; validate a relocated release."""

import argparse
import ctypes
import json
import msvcrt
import struct
import subprocess
from ctypes import wintypes
from pathlib import Path
from typing import Any

from validate_release import validate


def sparse_wave(path: Path, data_bytes: int = 4 * 1024**3) -> None:
    # RF64 allows >4 GiB. Mark sparse before extending; no multi-GiB allocation.
    header = (
        b"RF64\xff\xff\xff\xffWAVEds64"
        + struct.pack("<IQQQI", 28, data_bytes + 72, data_bytes, data_bytes // 4, 0)
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 2, 48000, 192000, 4, 16)
        + b"data\xff\xff\xff\xff"
    )
    with path.open("xb") as stream:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.DeviceIoControl.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        returned = wintypes.DWORD()
        if not kernel.DeviceIoControl(
            msvcrt.get_osfhandle(stream.fileno()),
            0x900C4,
            None,
            0,
            None,
            0,
            ctypes.byref(returned),
            None,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        stream.write(header)
        stream.seek(len(header) + data_bytes - 1)
        stream.write(b"\0")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("distribution", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    distribution = args.distribution.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    ffmpeg = distribution / "resources/engine/ffmpeg/ffmpeg.exe"
    engine = distribution / "resources/engine/mediaqc-engine.exe"
    machine = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "@{cpu=(Get-CimInstance Win32_Processor | Select-Object "
            "Name,NumberOfCores,NumberOfLogicalProcessors);"
            "ram=(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory;"
            "os=(Get-CimInstance Win32_OperatingSystem | "
            "Select-Object Caption,Version);"
            "gpu=(Get-CimInstance Win32_VideoController | Select-Object Name)} "
            "| ConvertTo-Json -Depth 5",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    (output / "machine.json").write_text(machine.stdout, encoding="utf-8")
    results: list[dict[str, Any]] = []
    for width, height, seconds in (
        (1920, 1080, 30),
        (1920, 1080, 120),
        (3840, 2160, 15),
    ):
        source = output / f"cpu-{width}x{height}-{seconds}s.mp4"
        subprocess.run(
            [
                str(ffmpeg),
                "-nostdin",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"testsrc2=size={width}x{height}:rate=25",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=997:sample_rate=48000",
                "-t",
                str(seconds),
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ac",
                "2",
                str(source),
            ],
            check=True,
            timeout=300,
        )
        result = validate(engine, source, output / source.stem, False)
        result["duration_seconds"] = seconds
        result["processing_ratio_media_over_wall"] = (
            seconds / result["analysis_seconds"]
        )
        result["realtime_objective_met"] = (
            result["processing_ratio_media_over_wall"] >= 1
        )
        result["cpu_only_analysis"] = (
            "Software decode/DSP; no hardware accelerator requested; AI OFF"
        )
        results.append(result)
        (output / "benchmarks.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )
        print(
            source.name,
            result["analysis_seconds"],
            result["sampled_peak_tree_private_bytes"],
            flush=True,
        )
    large = output / "sparse-4GiB.wav"
    sparse_wave(large)
    result = validate(engine, large, output / "sparse-cancel", True)
    result["duration_seconds"] = 4 * 1024**3 / 192000
    result["test_scope"] = (
        "Sparse RF64 inspection/active cancellation, not complete 6.2-hour QC"
    )
    result["no_full_source_copy"] = all(
        path.stat().st_size < large.stat().st_size
        for path in (output / "sparse-cancel/project").rglob("*")
        if path.is_file()
    )
    assert result["no_full_source_copy"]
    results.append(result)
    (output / "benchmarks.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
