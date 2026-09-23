# Phase 10 implementation handoff

This document records the earlier implementation handoff. Final automated release
validation is recorded in [Phase 10 validation](PHASE_10_VALIDATION.md).

Branch: `phase/10-batch-ux`. Specification package: **1.1.0**.
Implementation and focused validation are complete. Changes are uncommitted.
No dependencies were installed; no release build, packaging, full quality gate,
commit, or push was performed.

## Implemented behavior

- SQLite schema 3 migrations with committed-WAL backups and rollback. Batches,
  queue items, and summary report references are persisted separately from QC runs.
  Run creation and item linkage are transactional. Historical runs remain intact.
- Asynchronous folder discovery admits exactly WAV, MP3, MP4, and MXF,
  case-insensitively. Recursion defaults off. Links/junctions and project artifacts
  are excluded; duplicate normalized paths and import exclusions remain inspectable.
  Explicit file selection retains probe-based format handling.
- One engine-owned sequential coordinator shares scheduling/cancellation ownership
  with the existing run pipeline. Pending files do not have pre-created runs.
  Pause finishes the active file, with PAUSING represented until it settles.
  Resume uses saved settings. Stop cancels active/pending work and preserves
  committed completions, including the terminal-commit race.
- Recovery reconciles stale items with authoritative runs. Interrupted active work
  is not resumed mid-file; pending files require explicit continuation. Interrupted
  discovery requires reimport. Retries create a new batch with original references.
- Media errors remain per-file ERROR, without QC verdicts. Infrastructure/storage
  failure stops scheduling and is surfaced even when it cannot be persisted.
  Probe diagnostics are retained in project-local logs. A probe-output cursor race
  exposed by the real 137-file test was fixed without changing detector mathematics.
- The compact dashboard uses SQLite filters and 50-row pages, compact project reads,
  counts/progress/current filename, and Pause/Resume/Stop. Only a selected run is
  loaded for drill-down; evidence remains scoped to the selected finding.
  Technical Details is initially collapsed. Existing evidence, timelines,
  dispositions, notes, and detailed report access remain available.
- Measured-versus-threshold explanations derive deterministically from saved
  values. Unknown/contextual schemas retain saved prose and labeled measurements.
  No AI runtime, detector mathematics, or policy thresholds were changed.
- Compact HTML/PDF batch summaries use saved state/counts/profile/revision,
  include one processing-member entry per file, and separate import exclusions.
  Incomplete exports are explicit; existing per-run HTML/PDF reports remain valid.

## Database and IPC

New tables: `batches`, `batch_items`, and `batch_reports`, with queue/state indexes
and unique normalized-path, queue-position, and run-link constraints.

Added `batch.create`, `batch.list`, `batch.get`, `batch.items`, `batch.start`,
`batch.pause`, `batch.resume`, `batch.stop`, `batch.retry`, and
`batch.report.generate`; `analysis.list` exposes bounded historical-run pages.
Project reads accept compact mode. Capabilities advertise schema 3, the four
discovery extensions, maximum concurrency 1, and page size 50.

Batch discovery/status/item/progress/terminal/interrupted notifications carry
revision/session/sequence information. Dispositions update batch revisions in the
same transaction. The desktop allowlist and folder picker support the new methods.
Snapshots recover dropped events; progress ticks do not reload unchanged pages.

## Focused validation

Results were accumulated across focused runs; unchanged expensive tests were not
repeated after passing. No full repository gate was run.

| Validation                                                         | Result                                           |
| ------------------------------------------------------------------ | ------------------------------------------------ |
| Initial batch/project/job/IPC/AI integration selection             | 124 passed                                       |
| Expanded batch suite, including real 137-file queue                | 20 passed                                        |
| Additional storage and saved-threshold adapters                    | Passed; included in a 10-test targeted run       |
| Affected diagnostic/retry/recovery/storage paths after final fixes | 6 passed                                         |
| New disposition revision/filter and null/nonfinite regressions     | 4 passed                                         |
| Existing detailed report suite                                     | 11 passed                                        |
| Final AudioResults/Results selection                               | 20 passed                                        |
| Final BatchView selection, including progress invalidation         | 4 passed                                         |
| Earlier project/dashboard compatibility selections                 | Passed after the compact-project test adjustment |
| Python focused Ruff, formatting, and strict mypy                   | Passed                                           |
| Frontend changed-file ESLint/Prettier and TypeScript checks        | Passed                                           |
| Rust formatting and offline locked all-targets cargo check         | Passed                                           |
| Specification manifest validation and diff whitespace check        | Passed                                           |

The batch cases cover migration rollback, recovery before/after run completion,
137 real files, one active file, mixed WAV/MP3/MP4/MXF input, corrupt/changed media,
explicit-file extension compatibility, recursion/link exclusion/partial import,
bounded pagination, Pause/Resume, Stop after 127 of 150 files, ownership conflicts,
Stop versus committed completion, missing tools/storage failure, retry/report
preservation, source hashes/timestamps, and deterministic explanation boundaries.
Link/access-denial scenarios use deterministic filesystem doubles; clean-machine
Windows junction/deployment behavior remains part of final acceptance validation.

Principal commands used:

```text
.venv/Scripts/python.exe -m pytest engine/tests/test_batches.py -q --tb=short
.venv/Scripts/python.exe -m pytest engine/tests/test_reports.py -q --tb=short
.venv/Scripts/python.exe -m mypy engine/src/mediaqc_engine engine/tests/test_batches.py --follow-imports=silent
.venv/Scripts/python.exe -m ruff check <affected Python paths>
.venv/Scripts/python.exe -m ruff format --check <affected Python paths>
npm test --workspace @mediaqc/frontend -- tests/AudioResults.test.tsx tests/Results.test.tsx
npm test --workspace @mediaqc/frontend -- tests/BatchView.test.tsx
npm run typecheck
node_modules/.bin/eslint.cmd <changed frontend paths> --max-warnings 0
node_modules/.bin/prettier.cmd --config config/prettier.json --check <changed frontend paths>
cargo fmt --all --manifest-path apps/desktop/src-tauri/Cargo.toml -- --check
cargo check --locked --all-targets --manifest-path apps/desktop/src-tauri/Cargo.toml
git diff --check
```

Later batch runs used `-k` selections for changed paths, avoiding another 137-file
run. Rust commands used the existing repository toolchain with offline mode.

## Changed files

This inventory includes the approved specification amendments already present
when implementation resumed, as well as implementation and test changes.

**Engine — new:**

- `engine/src/mediaqc_engine/db/migration_003.sql`
- `engine/src/mediaqc_engine/db/batches.py`
- `engine/src/mediaqc_engine/jobs/discovery.py`
- `engine/src/mediaqc_engine/jobs/batch_manager.py`
- `engine/src/mediaqc_engine/explanations.py`
- `engine/src/mediaqc_engine/batch_reports.py`
- `engine/tests/test_batches.py`

**Engine — modified:**

- `engine/src/mediaqc_engine/app/projects.py`
- `engine/src/mediaqc_engine/app/system.py`
- `engine/src/mediaqc_engine/db/project.py`
- `engine/src/mediaqc_engine/db/runs.py`
- `engine/src/mediaqc_engine/db/findings.py`
- `engine/src/mediaqc_engine/jobs/manager.py`
- `engine/src/mediaqc_engine/jobs/recovery.py`
- `engine/src/mediaqc_engine/ipc/server.py`
- `engine/src/mediaqc_engine/media/tools.py`
- `engine/src/mediaqc_engine/reports.py`
- `engine/tests/test_ai.py`
- `engine/tests/test_ipc.py`
- `engine/tests/test_projects.py`
- `tools/smoke_engine.py`

**Desktop/frontend — new:**

- `apps/frontend/src/BatchView.tsx`
- `apps/frontend/src/FileResults.tsx`
- `apps/frontend/src/batches.ts`
- `apps/frontend/tests/BatchView.test.tsx`

**Desktop/frontend — modified:**

- `apps/desktop/src-tauri/src/engine.rs`
- `apps/desktop/src-tauri/src/main.rs`
- `apps/frontend/src/App.tsx`
- `apps/frontend/src/ProjectView.tsx`
- `apps/frontend/src/AudioResults.tsx`
- `apps/frontend/src/EvidenceView.tsx`
- `apps/frontend/src/jobs.ts`
- `apps/frontend/src/projects.ts`
- `apps/frontend/src/styles.css`
- `apps/frontend/tests/AudioResults.test.tsx`
- `apps/frontend/tests/Projects.test.tsx`
- `apps/frontend/tests/Results.test.tsx`

**Specifications/documentation:**

- `MASTER_SPEC.md`
- `SPEC_MANIFEST.json`
- `specs/01_PRODUCT_SPEC.md`
- `specs/02_ARCHITECTURE.md`
- `specs/03_DATABASE.md`
- `specs/06_IPC_SPEC.md`
- `specs/07_UI_SPEC.md`
- `specs/09_TESTING_SPEC.md`
- `specs/10_WINDOWS_BUILD.md`
- `docs/DEVELOPMENT.md`
- `docs/PHASE_10.md`

## Remaining validation and decisions

No known specification deviations or unresolved product/architecture decisions.
The branch is ready for **one explicitly approved final quality-gate/build/package
validation pass**. Release readiness is not yet established: full-gate integration,
packaged offline installer/relocated-portable workflows, clean-machine checks,
and representative long-media/performance validation remain deferred.
