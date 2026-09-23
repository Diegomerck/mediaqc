# 10 — Windows Build, Packaging, and Offline Distribution

**Version:** 1.1.0

## 1. Target

V1 required:

- Windows 10/11 x64.

ARM64 is not required for initial V1.

## 2. End-user prerequisites

The final installer SHALL NOT require the user to separately install:

- Python;
- Node.js/npm;
- Rust toolchain;
- Git;
- FFmpeg;
- SQLite;
- Visual Studio;
- CUDA.

System runtime dependencies required by Tauri/WebView2 must be handled according to supported Windows/Tauri installer behavior.

## 3. Build artifacts

Developer build produces:

- desktop executable;
- packaged engine executable/runtime;
- bundled FFmpeg;
- bundled ffprobe;
- built-in QC profile resources;
- report templates;
- installer;
- portable Windows x64 ZIP containing the complete application/resource folder.

Installer format may be MSI or NSIS/exe based on Tauri packaging decision.

The existing NSIS installer and portable ZIP remain first-class Phase 10 targets.
Phase 10 does not change the packaging toolchain or introduce runtime dependencies.

## 4. Resource layout

Conceptual installed resources:

```text
MediaQC/
  MediaQC.exe
  resources/
    engine/
      mediaqc-engine.exe
    ffmpeg/
      ffmpeg.exe
      ffprobe.exe
    profiles/
    report_templates/
```

Exact Tauri resource location may differ; runtime resolution must not depend on current working directory.

## 5. Engine packaging

Preferred V1 options:

- PyInstaller one-folder or equivalent standalone distribution;
- Nuitka or equivalent MAY be evaluated if startup/performance/security warrants it.

Avoid one-file self-extraction if it complicates antivirus behavior/startup without clear benefit.

Engine package SHALL include required Python libraries.

## 6. FFmpeg redistribution

Before public distribution, project owner SHALL verify the exact license obligations of the selected FFmpeg build and included codecs.

Build metadata SHALL record:
- FFmpeg build source/version;
- configuration flags;
- license notices required by that build.

Do not casually bundle a random third-party binary without provenance.

## 7. Application data

Recommended locations:

Global per-user app state/logs:
```text
%LOCALAPPDATA%\MediaQC\
```

Possible:
```text
settings.json
logs\
crash\
cache\
```

Projects live in user-selected directories and contain their own DB/evidence/reports.

## 8. Temp/cache

Default temp/cache:
```text
%LOCALAPPDATA%\MediaQC\cache
```

User SHALL be able to choose a different cache/temp directory because professional media workflows may require large fast storage.

Cache cleanup must never delete source media or reports.

## 9. Installer behavior

Installer SHOULD:
- install per-user when feasible;
- create Start Menu entry;
- optionally desktop shortcut;
- avoid admin rights when feasible;
- preserve user projects on uninstall.

Uninstall MUST NOT delete project directories unless user explicitly requests a separate cleanup action.

## 10. Offline behavior

The release build SHALL:
- make no required network call at startup;
- make no required network call during analysis;
- make no required network call during report generation.

Any optional update-check feature is out of V1 unless explicitly approved and must never block use.

## 11. Code signing

Production release SHOULD use Windows code signing.

Unsigned internal development builds are acceptable before public distribution.

Signing is packaging/reputation work, not a detector dependency.

## 12. Antivirus considerations

Packaging tests SHOULD be performed against Windows Defender.

Avoid:
- self-modifying behavior;
- hidden PowerShell;
- downloading executables at runtime;
- unnecessary process injection;
- opaque temporary extraction where possible.

## 13. Clean-machine release test

Test machine must not have project developer tools installed.

Validation:

1. install;
2. launch;
3. create project;
4. inspect sample;
5. run QC;
6. review evidence;
7. generate HTML;
8. generate PDF;
9. close/reopen;
10. uninstall;
11. verify source media/project retained as expected.

## 14. Version metadata

Expose in diagnostics:

- desktop app version;
- engine version;
- protocol version;
- database schema version;
- detector versions;
- FFmpeg/ffprobe versions.

## 15. Build reproducibility

Repository SHALL pin:

- JS dependencies;
- Rust/Tauri dependency versions;
- Python dependency versions;
- engine packaging config;
- FFmpeg distribution version/provenance.

Build script SHOULD produce a manifest of dependency/tool versions.

## 16. CI/CD

CI MAY run:
- TypeScript lint/test/build;
- Rust/Tauri checks;
- Python lint/type/test;
- synthetic fixture generation;
- engine packaging smoke test.

Public release packaging/signing may remain manual initially.

CI cloud use for developers is allowed; the shipped application itself remains offline-capable.

## 17. Acceptance criteria

- Installer works on clean Windows.
- No developer tools required after install.
- Bundled engine/FFmpeg resolve independent of PATH.
- App works with outbound network blocked.
- Uninstall does not delete projects/source media.
- Diagnostics show exact component versions.

## 18. Phase 10 installed and portable batch validation

Preserve the existing packaged Python engine, bundled FFmpeg/ffprobe, profiles,
numerical/reporting dependencies, and native process ownership. Include migration
003 when implemented. Specification version 1.1.0 is not an application-release
version bump; change runtime schema reporting to 3 only when that migration exists.
No production AI model/runtime is added; batch operation is fully usable with AI OFF.

The NSIS installer retains the offline Evergreen WebView2 installer arrangement.
The portable ZIP requires an already installed Evergreen WebView2 Runtime; it must
not download/install it at launch. Retain this prerequisite in release instructions.
No Python, Node/npm, Rust, Git, Visual Studio, FFmpeg, CUDA, service, or account may
become an end-user prerequisite. Do not infer portable independence from WebView2.

Projects live in user-selected writable directories outside application resources
and source-media directories. Batch DB rows, reports, evidence, logs, and caches
follow the existing project/application-data layout; no outputs beside source media.
Moving the portable application folder does not relocate original source paths;
missing/changed sources must remain explicit without discarding saved results.

For both installation and portable extraction on a clean Windows test machine,
with outbound network blocked and no developer tooling:

1. Launch with AI OFF and verify packaged tools resolve independently of PATH/CWD.
2. Open an existing schema-2 project, verify backup/migration and retained history.
3. Import mixed WAV/MP3/MP4/MXF plus unsupported/corrupt examples; review exclusions.
4. Run a 100+ file batch; verify sequential execution, dashboard counts, and paging.
5. Pause/Resume, inspect a completed file while another runs, and review evidence.
6. Stop during active work; verify no owned orphan processes and retained results.
7. Reopen saved batches; export per-run and compact batch HTML/PDF offline.
8. Simulate unexpected termination; explicitly continue pending work after recovery.
9. Check source immutability and bounded engine/child/UI resource behavior.
10. Relocate the extracted portable folder (including spaces/Unicode) and repeat
    open/review/start checks with unchanged external project/source locations.
11. Verify uninstall/application-folder removal retains external projects and sources.

Record versions, fixture composition, environment/prerequisites, outputs, and limits
in Phase 10 release evidence. Existing Phase 9 validation is a baseline, not evidence
that new batch behavior passed. This amendment alone authorizes no build/package run.
