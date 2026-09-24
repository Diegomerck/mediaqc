# Phase 10 final validation

Automated validation: **PASS**. Complete clean-machine release acceptance:
**UNVERIFIED**, pending the manual checks below. No commit, push, merge, dependency
installation/download, or git-history modification was performed.

## Optimization release closeout — 2026-09-24

The optimized installed build completed the operator's same four-file MP3/WAV/
MP4/MXF batch with General Technical QC 1.2.0 and AI OFF in **210.0 seconds**
(reported local time 11:08:30–11:12:00). Original installed time was 358.7 seconds;
the separate development-engine comparison was 238.3 seconds. The observed
installed-to-installed reduction is approximately **41.5%**. This is a manual,
single-run observation, not a controlled benchmark. See
[performance closeout](PHASE_10_PERFORMANCE_FIX.md) for methodology and limits.

Current validation: 330 Python tests (including 30 batch cases), 44 frontend,
3 baseline, and 6 Rust unit + 12 integration tests passed. The full gate ran once;
its sole failure was CRLF formatting in 14 otherwise unchanged working-tree files.
All 14 pass in HEAD with the actual repository Prettier configuration. LF-only
corrections and the formatting-only rerun passed; all 22 requirements are satisfied
without repeating successful suites or builds. No detector/profile recalibration
or verdict change was made.

Fresh NSIS/portable packaging and relocated WAV/MP3/MP4/MXF acceptance passed,
including source/resource immutability, cancellation/retry, saved results/evidence,
reopen, HTML/PDF reports, corrupt media, and unavailable-AI fallback. Verified the
ZIP checksum, all 311 manifest files, and embedded optimization/safeguard bytecode.
Cached NSIS and offline Evergreen WebView2 were retained; portable still requires
installed Evergreen WebView2. No dependencies were downloaded or installed.

Current artifacts (supersede the historical artifact identities below):

- Installer: `apps/desktop/src-tauri/target/release/bundle/nsis/MediaQC_0.0.0_x64-setup.exe`
  — 342,268,929 bytes.
  SHA-256: `4aedace7b99c274e643eaf21776a351c5479bbd375aa719faf9a83e0924e6c2b`.
- Portable: `dist/MediaQC-20260924T165718Z-portable-x64.zip`
  — 180,331,700 bytes; SHA-256 sidecar alongside it.
  SHA-256: `51ad322578e78f2e8e6efcb1dd459ad0305352b6d0d72844effbcc91390b7c5d`.

Local evidence is ignored under `.cache/`: `phase10-optimization-final-gate.log`,
`phase10-format-maintenance-gate.log`, `phase10-optimization-final-artifacts.json`,
`phase10-optimization-artifact-verification.json`, and
`phase10-optimization-packaged-acceptance/summary.json`. The manual benchmark is
the operator's report, not a new automated run or an independent finding re-audit.

Remaining clean-machine/firewall/uninstall and resource acceptance listed below
is still open. A larger known-good/known-bad detector reference corpus and separate
profile calibration are also outstanding; four operator-designated clean samples
do not establish universal thresholds. Current uncommitted work is on `main`;
the branch/status snapshot below is historical, not the current commit inventory.

## Historical initial Phase 10 validation

The remaining record describes the earlier release before the runtime fixes and
performance work. Counts, artifact identities, and working-tree status here are
retained as historical evidence, not current release claims.

### Previously completed and retained

- All 22 repository gate stages passed, combining the original gate with only
  failed/environment-blocked portions rerun. See `.cache/phase10-final-gate-summary.json`.
- Python: **322 passed**, including **30 Phase 10 cases**.
- Frontend: **43 passed** across seven test files. Repository baseline: **3 passed**.
- Rust: **4 unit + 12 integration tests passed**; check, Clippy, and formatting passed.
- Formatting, lint, TypeScript, and Python type checking passed (72 Python files).
- Engine/frontend/release builds and engine/native/Phase 2–5 smokes passed.
- AI-unavailable fallback, source integrity, cancellation, and persistence passed.
- Installer and portable packaging completed successfully after the interruption;
  their successful exit records were reused, not rebuilt during continuation.

## Completed during continuation

- Portable ZIP CRC, SHA-256 sidecar, and every manifest file size/hash passed.
- Extracted into `.cache/Phase10 relocated é/MediaQC-20260922T191253Z-portable-x64`.
  Portable desktop launched with empty PATH/PYTHONPATH/PYTHONHOME, showed a
  responsive MediaQC window, and closed gracefully. This is startup evidence,
  not an interactive workflow or clean-machine acceptance result.
- Packaged schema-2 migration retained real run/report history; schema 3 was exposed.
- Packaged unavailable LOCAL AI persisted UNAVAILABLE advice while QC completed.
- Packaged batch: **138 processed = 137 PASS + 1 expected corrupt-file ERROR**;
  two unsupported entries were excluded. Exactly one active item/run, no bulk
  pre-created runs, Pause/Resume, 50-row pagination, filters, and HTML/PDF passed.
- Stop, retry, forced termination, reopen/reconciliation, and explicit pending-file
  continuation passed. Completed history remained intact; interrupted work became
  ERROR without a QC verdict; pending files were not automatically resumed.
- Source identity was checked against 139 persisted inspection records and again
  before/after the remaining recovery scenario. Distribution resources stayed
  unchanged. Long-media tests separately checked complete source hashes/timestamps.
- New validation runner passed Ruff formatting/lint and mypy. Production code
  was not changed during this continuation, so passed builds/suites were not rerun.

## Failures and minimal corrections

1. Earlier gate sandbox access blocked `.pytest_cache` traversal and the cached
   uv launcher. Affected stages passed outside the sandbox, without installation.
2. Eight existing release/configuration files needed formatting-only corrections.
   The formatting stage then passed; no checks were weakened.
3. The new packaged runner initially used the wrong capability field and assumed
   AI reviews linked directly to runs. Corrected it to `schema_version` and the
   existing `ai_reviews → findings → analysis_runs` relationship.
4. Sandbox process termination blocked the crash test after the large batch passed.
   Only the remaining three-file control/recovery scenario was resumed with process
   permissions using `.cache/phase10_finish.py`. The large batch was not repeated.
5. Sandbox WMI returned empty hardware metadata. Collected that metadata separately
   with permission; benchmarks were not repeated.

The interrupted runner did not retain its bulk-queue memory time series. Do not
infer measured long-term queue/WebView memory stability from this run. Structural
tests and the separate long-media measurements passed; repeated-queue/UI resource
acceptance remains outstanding.

## CPU-only measurements

Windows 11 Pro 10.0.22631; i7-7700HQ, 4 cores/8 threads; 25,598,558,208 bytes RAM.
GPUs are installed, but these runs used software decoding/DSP and AI OFF.
Memory is sampled process-tree private bytes, not an exact high-water mark.

| Fixture           | Result    | Analysis time | Media/wall ratio | Sampled peak private bytes |
| ----------------- | --------- | ------------- | ---------------- | -------------------------- |
| 1080p, 30 s       | COMPLETED | 18.797 s      | 1.596×           | 417,394,688                |
| 1080p, 120 s      | COMPLETED | 66.938 s      | 1.793×           | 418,947,072                |
| 4K, 15 s          | COMPLETED | 14.953 s      | 1.003×           | 624,783,360                |
| Sparse 4-GiB RF64 | CANCELLED | 2.172 s       | Not applicable   | 336,072,704                |

All four passed source integrity, reopen, and no-owned-child checks. RF64 also
passed no-full-source-copy; this was cancellation, not complete six-hour QC.

## Artifacts

- Installer: `apps/desktop/src-tauri/target/release/bundle/nsis/MediaQC_0.0.0_x64-setup.exe`
  — 342,294,918 bytes; unsigned internal build.
  SHA-256: `a42045d1d8897ab67a28958bab710c4b6a6799c6f51da836a01a8f63574da214`.
- Portable: `dist/MediaQC-20260922T191253Z-portable-x64.zip`
  — 180,324,014 bytes; SHA-256 sidecar alongside it.
  SHA-256: `9f3042be6e9d4157475aed21d4d83cb76ecd90d842ef28a8656b44bf1968bc24`.
- Portable `release-manifest.json` verified against every extracted file.
  NSIS used the previously cached offline WebView2 installer; no downloads occurred.

Evidence: `.cache/phase10-final-build-results.json`, `phase10-installer-record.json`,
`phase10-desktop-launch.json`, `phase10-packaged-final/phase10-summary.json`,
`phase10-final-benchmarks/benchmarks.json`, and associated logs. Initial runner
failures remain in `phase10-packaged.log`, `phase10-packaged-verified.log`, and
`phase10-packaged-final.log`; successful recovery is in `phase10-finish.log`.

## Remaining acceptance and readiness

- Clean Windows 10/11 standard-user install/uninstall/reinstall, project/source
  retention, and WebView2 present/absent snapshots.
- Firewall-enforced offline operation with Defender/corporate controls enabled.
- Interactive packaged dashboard, evidence/dispositions/reports, responsiveness,
  and repeated-queue/long-MXF engine/child/WebView resource measurements.
- Physical CPU-only clean-machine acceptance. Portable still requires installed
  Evergreen WebView2; signing/public-distribution licensing remain release-owner work.

Ready to commit for review: **yes**. Unconditional Phase 10 acceptance/merge sign-off:
**not yet**; required manual/clean-machine acceptance remains unverified. No known
production-code defect was found by this continuation.

## Exact final working-tree status

```text
## phase/10-batch-ux...origin/phase/10-batch-ux
 M MASTER_SPEC.md
 M SPEC_MANIFEST.json
 M apps/desktop/package.json
 M apps/desktop/src-tauri/src/engine.rs
 M apps/desktop/src-tauri/src/main.rs
 M apps/desktop/src-tauri/tauri.prepared.conf.json
 M apps/desktop/src-tauri/tauri.release.conf.json
 M apps/frontend/src/App.tsx
 M apps/frontend/src/AudioResults.tsx
 M apps/frontend/src/EvidenceView.tsx
 M apps/frontend/src/ProjectView.tsx
 M apps/frontend/src/jobs.ts
 M apps/frontend/src/projects.ts
 M apps/frontend/src/styles.css
 M apps/frontend/tests/AudioResults.test.tsx
 M apps/frontend/tests/Projects.test.tsx
 M apps/frontend/tests/Results.test.tsx
 M config/windows-signing.example.json
 M docs/DEVELOPMENT.md
 M docs/PHASE_9.md
 M docs/WINDOWS_RELEASE.md
 M engine/src/mediaqc_engine/app/projects.py
 M engine/src/mediaqc_engine/app/system.py
 M engine/src/mediaqc_engine/db/findings.py
 M engine/src/mediaqc_engine/db/project.py
 M engine/src/mediaqc_engine/db/runs.py
 M engine/src/mediaqc_engine/ipc/server.py
 M engine/src/mediaqc_engine/jobs/manager.py
 M engine/src/mediaqc_engine/jobs/recovery.py
 M engine/src/mediaqc_engine/media/tools.py
 M engine/src/mediaqc_engine/reports.py
 M engine/tests/test_ai.py
 M engine/tests/test_ipc.py
 M engine/tests/test_projects.py
 M package.json
 M specs/01_PRODUCT_SPEC.md
 M specs/02_ARCHITECTURE.md
 M specs/03_DATABASE.md
 M specs/06_IPC_SPEC.md
 M specs/07_UI_SPEC.md
 M specs/09_TESTING_SPEC.md
 M specs/10_WINDOWS_BUILD.md
 M tools/check.mjs
 M tools/smoke_engine.py
?? apps/frontend/src/BatchView.tsx
?? apps/frontend/src/FileResults.tsx
?? apps/frontend/src/batches.ts
?? apps/frontend/tests/BatchView.test.tsx
?? docs/PHASE_10.md
?? docs/PHASE_10_VALIDATION.md
?? engine/src/mediaqc_engine/batch_reports.py
?? engine/src/mediaqc_engine/db/batches.py
?? engine/src/mediaqc_engine/db/migration_003.sql
?? engine/src/mediaqc_engine/explanations.py
?? engine/src/mediaqc_engine/jobs/batch_manager.py
?? engine/src/mediaqc_engine/jobs/discovery.py
?? engine/tests/test_batches.py
?? tools/smoke_phase10.py
```
