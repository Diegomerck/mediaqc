# Phase 9 — Windows packaging and performance

Validated on 2026-09-20 UTC. Implementation and artifacts are uncommitted on
`phase/09-windows-release`. This is an unsigned internal V1 candidate, version
0.0.0. V1 release acceptance is **not complete**: clean-machine, firewall and
uninstall validation remain outstanding. No production AI runtime/model was added.

## Deliverables

| Phase 9 deliverable                  | Result     | Evidence and limits                                                                                                                                                                   |
| ------------------------------------ | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Signed-ready installer configuration | PASS       | Separate NSIS release config, current-user install, SHA-256 signing configuration template. Actual installer/desktop are NotSigned; no credentials supplied.                          |
| Bundled engine                       | PASS       | PyInstaller one-folder Python 3.12.14 runtime; relocated packaged smokes pass with PATH/PYTHONPATH empty.                                                                             |
| Bundled FFmpeg/ffprobe               | PASS       | Existing pinned Gyan 8.1.2 binaries, LICENSE, README and build provenance included.                                                                                                   |
| Clean-machine installation test      | UNVERIFIED | Reproducible procedure supplied; this developer PC cannot prove absence of developer/runtime dependencies.                                                                            |
| Uninstall test                       | UNVERIFIED | Generated NSIS removal script reviewed; no physical install/uninstall performed. Projects must be outside installed resources/app-data cleanup locations.                             |
| CPU-only test                        | PASS       | Software decode/DSP, AI OFF; all benchmark runs succeeded. Physical GPU-free Windows machine remains UNVERIFIED.                                                                      |
| Offline test                         | UNVERIFIED | No required runtime downloads introduced; empty developer paths and packaged reports pass. Network disconnection and firewall enforcement were not performed.                         |
| Large-file test                      | PASS       | Sparse >4-GiB RF64 inspection/cancellation, source integrity, no source copy, no owned children, persisted CANCELLED/reopen. Short/long complete QC memory comparison below.          |
| Portable Windows target              | PASS       | Self-contained application-owned dependencies in ZIP; extracted outside repository, GUI launch and WAV/MP3/MP4/MXF QC pass. Installed Evergreen WebView2 is an explicit prerequisite. |

## Artifacts and dependency inventory

Paths are relative to `C:\Dev\MediaQC\mediaqc` in this report.

| Artifact                                       | Path                                                                            | Size                                                                     |
| ---------------------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| NSIS installer                                 | `apps/desktop/src-tauri/target/release/bundle/nsis/MediaQC_0.0.0_x64-setup.exe` | 342,231,492 bytes / 326.38 MiB                                           |
| Portable ZIP                                   | `dist/MediaQC-20260920T012853Z-portable-x64.zip`                                | 180,284,109 bytes / 171.93 MiB                                           |
| Portable folder                                | `dist/MediaQC-20260920T012853Z-portable-x64/`                                   | Full executable/resource layout                                          |
| Artifact SHA-256 and WebView2 setup provenance | `dist/phase9-artifacts.json`                                                    | Installer and ZIP hashes; Microsoft setup signature/version/hash         |
| Per-file dependency inventory                  | `dist/MediaQC-20260920T012853Z-portable-x64/release-manifest.json`              | File paths/sizes/hashes, Python dependencies, FFmpeg build configuration |

Installer SHA-256: `684bc89a6a08870cd3e62a5390bf4b006a9632e9150da8751b20987dea3a8d74`.
Portable ZIP SHA-256: `b36af30348f4b7fcb2c101cca97ccbef15ea7321b97d0bca4eaf6cfeeac6928d`.

Bundled components include the compiled Tauri 2.11.5/React frontend, CPython 3.12.14,
SQLite, NumPy 2.4.1, SciPy 1.17.0, OpenCV headless 4.13.0.92, ReportLab 4.4.10,
Pillow 12.3.0, charset-normalizer 3.5.1, required DLLs including VC runtimes,
FFmpeg/ffprobe 8.1.2, built-in profiles and reporting resources/fonts. Python's license
and numerical/reporting dependency metadata/licenses are included. JS/Rust/Python
lockfiles accompany the portable artifact. PyInstaller 6.19.0 is the build packager.
Node/npm, Rust, Git, Visual Studio and CUDA are not application runtime dependencies.

The installer embeds Microsoft's 213,053,648-byte Evergreen offline setup executable,
whose Authenticode signature verified Valid. Setup file version is 1.3.269.9; this
is **not a claim about the embedded browser runtime version**. Its SHA-256 is
`ad9b350625e132481bc0953eee9e032810134df9fedbd7be364c3f4e0e4dbd64`.
Tauri obtains Evergreen setup at build time; archive this exact payload for repeatable
distribution. A future packaging run can retrieve a newer payload. The portable ZIP
does not contain it and does not download it. No fixed WebView2 runtime was introduced.

Signing readiness is configuration/documentation readiness, not a signed release.
Use the local certificate/timestamp override documented in WINDOWS_RELEASE.md and
verify nested application-owned binaries plus installer. Public redistribution also
requires the owner's FFmpeg GPL/codecs/source-availability and dependency-license review.

## Validation and counts

Focused Phase 9 tests: **4 passed**: offline/per-user release config, relocatable ZIP
layout and integrity/tamper detection, missing-runtime rejection before output, and
Windows process-tree memory accounting including a real child process.

The complete gate ran **once**. Its recorded result was 20/22 gates passing and exit
1 due to Prettier line endings in six existing Phase 8 files and Ruff formatting in
the modified engine build script. Both were corrected and only the affected formatter
checks rerun; both passed. All functional checks passed on the original gate run.
No full gate, installer creation or benchmark run was repeated.

Repository test totals: **350 passed** = 292 Python + 39 frontend + 16 Rust + 3 Node
repository tests. The focused four are included in the Python count, not additional.
Packaged smoke scenarios and benchmarks are not counted as repository unit tests.
New validation tooling also passed targeted Ruff and strict mypy checks.

Commands executed:

```text
.venv/Scripts/python.exe -m pytest engine/tests/test_windows_release.py -q
npm run check
npm run format:check
.venv/Scripts/python.exe -m ruff format --check .
npm run release:installer
.venv/Scripts/python.exe tools/package_windows.py
.venv/Scripts/python.exe tools/smoke_release.py <extracted-distribution> --output .cache/phase9-relocated-smoke
.venv/Scripts/python.exe tools/benchmark_release.py <extracted-distribution> --output .cache/phase9-benchmarks
```

The full gate used cached/offline uv and Cargo toolchains. It compiled the desktop
release once using already-prepared engine/frontend assets; installer creation then
used `tauri bundle` without recompilation. Each final distribution was assembled once.

Existing standalone protocol, native lifecycle and Phase 2–8 packaged smokes all
passed. The relocated release additionally passed WAV/MP4/MXF production-controller
scenarios (including evidence, dispositions, HTML/PDF, cancellation/retry, history,
AI unavailable equivalence), MP3 QC/report/reopen, corrupt media rejection with
continued engine usability, source SHA-256/size/mtime and resource-tree integrity.

ZIP extracted outside the repository to
`%TEMP%\MediaQC Phase9 extracted 20260920\MediaQC-20260920T012853Z-portable-x64`.
Its MediaQC.exe launched from another working directory with empty PATH/PYTHONPATH,
created a responsive MediaQC window and closed gracefully. Installed Evergreen
WebView2 153.0.4234.48 supplied the prerequisite. The bundled file inventory was
unchanged after GUI launch. This is a launch check, not a visual end-to-end UI review
or proof of responsiveness during long QC. No missing-WebView2 snapshot was tested.

## CPU and bounded-memory results

Machine: Intel Core i7-7700HQ, 4 cores / 8 logical CPUs, 25,598,558,208 bytes RAM
(23.84 GiB), Windows 11 Pro 10.0.22631. Intel HD 630 and NVIDIA 940MX are installed;
analysis used software decode/CPU DSP without hardware acceleration, CUDA or AI.
These measurements do not replace a physically GPU-free clean-machine test.

Generated MP4 media: H.264/libx264 ultrafast CRF 23, yuv420p, 25 fps, stereo 48-kHz
AAC sine audio. The unchanged general_technical_qc 1.2.0 profile ran the applicable
deterministic detector suite with AI OFF, every frame and profile-controlled 320x180
spatial measurements. No frame dropping, threshold change or correctness optimization
was introduced. Analysis timing includes QC/evidence and excludes report export.

| Fixture                               |         Bytes |    Duration | Inspection |                      QC wall time | Media/wall ratio | Sampled tree WS / private peak |
| ------------------------------------- | ------------: | ----------: | ---------: | --------------------------------: | ---------------: | -----------------------------: |
| 1920x1080 MP4                         |    51,784,784 |        30 s |    0.125 s |                          16.375 s |            1.83x |              157.3 / 397.3 MiB |
| 1920x1080 MP4                         |   207,069,712 |       120 s |    0.125 s |                          64.031 s |            1.87x |              159.2 / 399.4 MiB |
| 3840x2160 MP4                         |   106,234,267 |        15 s |    0.141 s |                          13.375 s |            1.12x |              349.1 / 594.9 MiB |
| Sparse RF64 PCM, stereo 48-kHz 16-bit | 4,294,967,376 | 22,369.62 s |    0.156 s | 2.125 s to requested cancellation |   Not applicable |               81.6 / 320.7 MiB |

Real-time objective: **met on both tested 1080p samples**, also on this 4K sample.
Metadata inspection objective: met on all four fixtures. Four times the 1080p source
duration/size increased sampled peak private memory by only 0.53%, consistent with
the existing window/frame-based processing. Sampling interval was 100 ms over engine
and descendants; these are sampled peaks, not exact high-water marks or a proof for
every codec/pathological file. The comparison intentionally retains the same profile.

The RF64 file was sparse before extension: fsutil reported allocated ranges only
at the header (0x10000 bytes) and the final 0x50 bytes. It was not physically filled
with four GiB of data. Inspection, active cancellation, persisted CANCELLED, fresh
process reopen, no remaining owned processes and no full source copy all passed.
Complete six-hour analysis was not attempted. All benchmark sources retained exact
SHA-256, size and mtime. All completed benchmarks exported both report formats and
reopened their projects successfully.

Decoded frames/PCM remain bounded; per-frame feature/timestamp caches live on disk
inside the selected project and may grow with duration. A separate global cache-root
setting is not implemented; choosing the project location selects its cache volume.

## Global V1 acceptance matrix

PASS here describes verified code/tests or tested artifacts, not the untested
Windows deployment matrix.

| Global criterion                                           | Result     | Evidence/limit                                                                                                                                       |
| ---------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Clean Windows 10/11 installation without developer tooling | UNVERIFIED | Requires separate snapshots.                                                                                                                         |
| Launch with internet disconnected                          | UNVERIFIED | Portable launch passed with network state unchanged.                                                                                                 |
| Core QC with outbound network blocked                      | UNVERIFIED | Firewall enforcement not performed.                                                                                                                  |
| Source media unchanged                                     | PASS       | Hash, size and nanosecond mtime checks on smoke/benchmark fixtures.                                                                                  |
| Projects persist and reopen                                | PASS       | Fresh process/controller restart and saved history.                                                                                                  |
| User can select QC profile                                 | PASS       | Existing UI tests and packaged profile selection/snapshot checks.                                                                                    |
| Structured audio/video findings                            | PASS       | Regression suite and WAV/MP3/MP4/MXF smokes.                                                                                                         |
| WARN/FAIL context, measurements and evidence/error         | PASS       | Existing regression coverage and packaged evidence reads.                                                                                            |
| Confirmed/false-positive/ignored dispositions              | PASS       | Production-controller smokes and persistence tests.                                                                                                  |
| Overall result follows dispositions                        | PASS       | Existing engine/frontend regression checks.                                                                                                          |
| HTML and PDF exports                                       | PASS       | Packaged exports and byte-identical reopen checks.                                                                                                   |
| Corrupt/unsupported media does not crash app               | PASS       | Structured engine errors, subsequent ping, existing UI/error/lifecycle tests.                                                                        |
| Cancellation terminates owned workers/media processes      | PASS       | Native lifecycle tests and sparse-file terminal process-tree check.                                                                                  |
| Policy thresholds remain in profiles                       | PASS       | No production detector/profile/threshold changes; existing profile tests pass.                                                                       |
| Synthetic regression corpus                                | PASS       | Full 292-test engine suite including audio/video fixtures.                                                                                           |
| Curated clean corpus false-positive budgets                | UNVERIFIED | Prior Phase 5 video corpus passed within its documented small scope; audio budget remains unadjudicated. No expanded corpus claim.                   |
| AI entirely disabled                                       | PASS       | OFF benchmarks, missing-provider smokes; no production model bundled.                                                                                |
| Installer bundles required runtime dependencies            | PASS       | Python/DLL/media tools/resources plus signed Microsoft offline WebView2 setup in generated NSIS payload. Installed compatibility remains unverified. |
| No core account sign-in/cloud service dependency           | PASS       | Preserved local stdio/SQLite architecture and packaged deterministic workflows.                                                                      |

## Remaining release validation and records

Run the exact [clean-machine procedure and PowerShell evidence commands](WINDOWS_RELEASE.md)
on clean Windows 10/11 with no developer tooling, including absent/present WebView2,
standard-user installation, network disconnection, firewall enforcement, reports,
retention after uninstall/reinstall, and portable prerequisite behavior. Record
Defender behavior and long-run UI responsiveness. Do not bypass endpoint controls.

Release blockers: those unverified deployment/offline criteria; production signing
credentials/reputation work before a signed release; owner redistribution-license
review; outstanding full curated audio false-positive acceptance. The separate
cache-root preference remains a documented limitation. No clean-machine, firewall,
physical uninstall, GPU-free hardware or missing-WebView2 success has been invented.

Retained local evidence:

- `.cache/phase9-quality-gate.log`, `phase9-format-recheck.log`, `phase9-python-format-recheck.log`.
- `.cache/phase9-installer.log`, `phase9-portable.log`, `phase9-webview2.json`.
- `.cache/phase9-relocated-smoke/summary.json`, native logs and MP3 result JSON.
- `.cache/phase9-desktop-launch.json`.
- `.cache/phase9-benchmarks/machine.json`, `benchmarks.json`, per-run result JSON,
  profiles, detector states, source fingerprints, projects, evidence and reports.

Changes: release/prepared Tauri configurations; signing example; release npm targets;
single-preparation full gate; Python license/dependency metadata collection;
relocatable native smoke resource/log paths; portable assembler/inventory;
Windows memory sampler, release smoke and benchmark runners; focused tests; release
documentation. No production analysis algorithms or architecture dependencies changed.
The six Phase 8 files flagged by Prettier have line-ending normalization only.
