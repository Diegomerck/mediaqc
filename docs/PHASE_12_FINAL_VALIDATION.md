# Phase 12 final automated validation

Final validation was authorized after approval of the V1 limitation disposition.
**All 22 repository gate requirements are satisfied. Automated Phase 12 work is
ready for commit/push/PR review; no Git publication was performed.** This does not
claim completion of the separate clean-machine/public-release acceptance matrix.
No new phase was started and no production detector/profile policy was changed.

## Full quality gate

The first sandbox launch stopped before tests/builds because directory scanning
could not access `.pytest_cache`. The authorized full gate then ran to completion
once: **21 PASS / 1 FAIL**, with only formatting failing. Normalizing seven files'
line endings and rerunning only `format:check` passed. The successful full test and
build stages were not repeated.

| Gate                     | Final result / evidence                                                      |
| ------------------------ | ---------------------------------------------------------------------------- |
| `format:check`           | PASS on isolated rerun; initial seven-file formatting failure retained       |
| `lint`                   | PASS, zero warnings                                                          |
| `typecheck`              | PASS                                                                         |
| `python:format:check`    | PASS                                                                         |
| `python:lint`            | PASS                                                                         |
| `python:typecheck`       | PASS, 95 source files                                                        |
| `python:test`            | PASS, 611 tests in 303.37 seconds                                            |
| `rust:format:check`      | PASS                                                                         |
| `test:baseline`          | PASS, 3 tests                                                                |
| `test:frontend`          | PASS, 44 tests in 7 files                                                    |
| `build`                  | PASS, static frontend                                                        |
| `engine:build`           | PASS, standalone PyInstaller runtime                                         |
| `engine:smoke`           | PASS, 10,000 sequential pings, clean shutdown, empty PATH                    |
| `rust:check`             | PASS, all targets                                                            |
| `rust:lint`              | PASS, Clippy with warnings denied                                            |
| `rust:test`              | PASS, 6 unit and 12 integration tests; empty main/doc targets pass           |
| `desktop:build:prepared` | PASS, optimized Windows executable                                           |
| `native:smoke`           | PASS, controller lifecycle and parent-death behavior                         |
| `phase2:smoke`           | PASS, inspection/restart/reopen/missing-media handling                       |
| `phase3:smoke`           | PASS, queue/cancel/retry/events/history                                      |
| `phase4:smoke`           | PASS, packaged audio, evidence, dispositions, HTML/PDF, optional-AI fallback |
| `phase5:smoke`           | PASS, packaged MP4/MXF, timing, evidence, cancel/retry/reopen                |

**676 test cases** = 611 Python + 44 frontend + 3 repository + 6 Rust unit +
12 Rust integration. The earlier 277 focused tests are a subset and are not added
again. Smoke workflows and 10,000 IPC pings are reported separately from test-case
counts. The six smoke stages in the gate all passed.

Logs: `.cache/phase12/full-quality-gate.log` (aborted sandbox launch),
`full-quality-gate-authorized.log` (one completed full gate), and
`format-check-rerun.log`.

## Isolated maintenance corrections

- `smoke_engine.py` and `smoke_phase10.py` still asserted schema 3. They now assert
  the specified/implemented schema 4. The synthetic schema-2 migration fixture
  removes schema-4 assignment tables before migration, matching the existing
  migration regressions. No production migration behavior changed.
- Seven existing frontend/Phase 10 files needed only line-ending normalization;
  `git diff --ignore-space-at-eol` showed no semantic changes for those files.
- Three misencoded characters in the testing specification were restored, and
  `SPEC_MANIFEST.json` byte counts updated. The original Unicode path in the engine
  smoke was also restored after detecting a text-encoding edit error.
- The affected engine smoke, three repository/specification checks, and focused
  Ruff formatting/lint/mypy checks passed. No broad test or release build rerun
  was necessary for these tooling/documentation corrections.

## Windows packaging and relocated smoke validation

The normal release procedure was followed after the successful prepared build:
NSIS packaging and portable assembly, with no rebuild of the application.
NSIS first hit a sandbox socket denial, then succeeded with the authorized access
needed for normal WebView2 packaging. Microsoft Evergreen offline installer was
downloaded at build time; this does not add a runtime network requirement.

Tauri emitted a bundle-type/updater metadata warning on the packaging retry after
the first attempt had already patched the executable. V1 has no updater. Packaging
completed and the resulting desktop/engine hashes match the relocated artifacts;
this warning is retained in the log, not hidden or treated as an application failure.

Artifacts:

- NSIS: `apps/desktop/src-tauri/target/release/bundle/nsis/MediaQC_0.0.0_x64-setup.exe`
  (341,513,356 bytes).
  SHA-256: `eb1917069d84107e0a7aa35ae7066a00ddac3b2cf7c5e6bfb98113e8b5a491af`.
- Portable: `dist/MediaQC-20261005T033147Z-portable-x64.zip`.
  SHA-256: `612ceb4eae1b5b3669f7cf0810a3ee06d6fcbffd2b1976392c52afa3e36c2909`.
- ZIP checksum and **all 313 manifest entries** verified after extraction to a fresh
  directory containing spaces and Unicode. Desktop and engine executables match
  the current successful release/engine builds.
- Detailed artifact and downloaded WebView2 version/hash records:
  `.cache/phase12/artifact-record.json` and `webview-build-record.json`.

Three supplemental packaged scenario groups passed with empty PATH/PYTHONPATH:

1. **Relocated release:** WAV/MP3/MP4/MXF through the native controller/engine,
   corrupt-media recovery, evidence, dispositions, HTML/PDF, reopen,
   source hash/size/mtime and resource immutability.
2. **Phase 12 applicability:** actual packaged schema 4 and policy resource loading;
   one required silent ISO remains WARN beneath active L/R, four unused/unknown
   channels retain INFO; channel waveform/spectrogram/metrics evidence loads;
   designated L/R and raw stream measurements remain distinct; HTML/PDF preserves
   the assignment; fresh-process reopen and retry retain the immutable snapshot.
   The 100001-sample EOF boundary, source identity and owned-child cleanup pass.
3. **Batch regression:** schema-2 history migration, unavailable-LOCAL fallback,
   138-item queue (137 PASS and one expected corrupt-media ERROR), pause/resume,
   single-active-file checks, 50/50/38 paging, report export and stop/retry passed.
   Windows then denied `taskkill` at the deliberate crash step. Only the three-item
   crash/recovery segment was rerun with required permission; the 138-item queue
   was not repeated. INTERRUPTED state, explicit continuation and retained completed
   history passed. The interrupted item remains an expected ERROR rather than
   being silently restarted; the two other items complete with expected silence WARNs.

Evidence: `.cache/phase12/packaged-release/summary.json`,
`packaged-applicability/summary.json`, and `packaged-batch-recovery/summary.json`.
The initial batch interruption and isolated rerun logs are retained. The initial
batch runner did not reach its final summary write; its earlier successful
assertions and persisted completed queue are explicitly distinguished from the
isolated continuation record. No missing aggregate summary is represented as a
successful uninterrupted run.

## Source and resource immutability

All completed source-immutability assertions passed. The release/applicability
smokes compared source SHA-256, size and modification time, and compared resource
inventories. For the interrupted batch smoke, every inspected fixture's persisted
pre-analysis fingerprint still matched; all those fixtures are small enough for
that fingerprint to include their entire contents. The isolated continuation also
passed before/after full SHA-256/size/mtime checks. All **143 expected source files**
remain, with no sidecars; unsupported/corrupt fixture content is unchanged.

Original WAV/MP3/MP4/MXF reference media and the historical reference project were
not opened or modified during this validation. Intentional source mutations in
negative identity regression tests affect only disposable generated fixtures.

## Limitations and remaining release work

All approved limitation binding/mutation tests passed within the 611-test suite.
The corpus record remains **42 executions: 30 strict PASS / 12 strict FAIL**, with
12 separately approved dispositions, no unexercised limitation entries and zero
unexpected release blockers. Counterexamples and original ground-truth annotations
remain intact. The original MXF transient near 7.567 s remains explicitly
NEEDS_INDEPENDENT_EVIDENCE/nonblocking; it is neither clean nor confirmed faulty.
See [the V1 disposition](PHASE_12_V1_ACCEPTANCE.md).

No unresolved functional regression was found by automated validation. The known
recall/specificity limitations remain real; acceptance does not claim their repair.

**Automated Phase 12 acceptance is complete and ready for commit/push/PR review.**
Unconditional V1 public-release sign-off remains outside that conclusion. Existing
clean Windows 10/11 install/uninstall/reinstall and retention checks, WebView2
present/absent cases, firewall-enforced offline operation, physical CPU-only and
interactive/long-duration resource acceptance remain unverified here. This pass
also does not establish a representative 30-minute clean-content false-positive
rate. Empty PATH and local smoke success do not substitute for those requirements.
No commit, push, merge, PR, installation into the user's existing application, or
next-phase work was performed.
