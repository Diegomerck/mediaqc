# Phase 7 — Reports

Completed runs support **Export HTML** and **Export PDF** from the analysis view,
including previous runs after reopening a project. The UI shows the resulting
absolute path. Artifacts live in the project's `reports/` directory; each export
gets a new filename and an entry in the existing `reports` table.

`report.generate` uses the documented `analysis_run_id` and `format` parameters.
Its response contains `id`, `analysis_run_id`, `format`, `relative_path`,
`absolute_path`, `generator_version`, and UTC `generated_at`. Invalid arguments
return `INVALID_REQUEST`; incomplete runs and rendering/storage errors return
`REPORT_FAILED`. An unknown run returns the existing `RUN_NOT_FOUND` error.

## Saved-data contract

One SQLite read transaction supplies the saved run, media identity, complete QC
profile snapshot, detector executions/versions, findings, feedback and evidence
references. Export does not start analysis, probe media, fingerprint the source,
or update dispositions. Overall result and contributing counts use the Phase 6
implementation: OPEN/CONFIRMED contribute; FALSE_POSITIVE/IGNORED do not. All
findings, including excluded findings, remain visible. Run, engine, protocol,
media-tool, detector, profile and generator versions are included when saved;
unavailable metadata is explicit.

For unchanged saved data and evidence, repeat HTML and PDF exports are
byte-identical, including across engine restart. Export IDs and wall-clock export
timestamps are stored in SQLite, outside the reproducible document content.
Reports reflect dispositions at export time; previously exported artifacts remain
unchanged. These are saved-run reports, not assertions about the current source.

Evidence references include availability and integrity results. Missing, changed,
unsupported or unverifiable artifacts are explicit. Images are referenced rather
than embedded; saved measurements, thresholds and evidence-generation errors stay
in the report. Evidence validation does not require the original media to exist.

## Offline packaging and limits

PDF rendering uses pinned ReportLab, its bundled Vera font and the existing
standalone engine. No browser, Node, separately installed Python, HTTP server,
cloud service, or subprocess is needed. ReportLab data/font/license resources are
collected during packaging. HTML is self-contained, escapes all saved text, and
uses a restrictive content security policy with no external resources.

PDF glyphs unsupported by the embedded font are visibly preserved as `\uXXXX`
or `\UXXXXXXXX` escapes; HTML retains full Unicode. This avoids silent missing
glyphs. PDF pages wrap long values and include page numbers.

Exports are bounded to 5,000 findings and 4 MiB of report text; larger exports fail
explicitly, never truncate. Evidence reads retain the existing 256 KiB per-artifact
limit. Rendering is synchronous and starts no owned child processes. Temporary
artifacts are published only after rendering succeeds; failures clean up output
and do not register a successful report. A forced process kill can leave an
unregistered temporary/orphan artifact, but cannot corrupt the saved run.

## Validation

Focused commands:

```powershell
.venv/Scripts/python.exe -m pytest engine/tests/test_reports.py engine/tests/test_evidence.py -q
npm test --workspace @mediaqc/frontend -- --run tests/ReportExport.test.tsx tests/Results.test.tsx
```

The production-controller audio and MP4/MXF packaged smokes also export both
formats, validate saved dispositions, restart the engine, and compare output bytes.
They retain empty end-user PATH/PYTHONPATH and source SHA-256/mtime assertions.
The complete repository gate is `npm run check`, including the Windows Tauri
release build and all packaged smokes.

Authoritative specifications and database schema are unchanged. No Phase 8+
functionality is included. Clean-machine installer/platform-matrix validation is
not established by these checks and remains later-phase work.

## Recorded validation — 2026-09-19

Phase 7 exit criteria from `MASTER_SPEC.md`:

- PASS: reports are reproducible from a saved project/run. Both formats compare
  byte-identical after reopening in focused tests and after engine restart in
  packaged audio, MP4 and MXF smokes.
- PASS: generation requires no internet. Focused tests reject socket/subprocess
  use and source-media reads; packaged exports run with empty PATH/PYTHONPATH.

All four deliverables are implemented: HTML, PDF, saved run/profile versions and
disposition-aware summaries. The generated ten-page PDF fixture was rendered and
visually checked for clipping, overlap, missing glyphs and page numbering.

Focused validation passed **59 distinct tests**: 11 reports, 32 existing evidence,
3 export UI and 13 existing results UI tests. The initial combined engine run
passed 41 tests; the final reports-only run passed 11, including two subsequently
added failure/missing-source tests. Successful unaffected tests were not repeated.

The full `npm run check` ran **once**, attempting all 22 gates. It initially
reported 18 PASS and four failures:

1. Prettier formatting in eight existing Phase 6 files: normalized formatting
   without semantic changes; `npm run format:check` then passed.
2. Two lint issues in the new export test: corrected; `npm run lint` then passed.
3. Python formatting in the edited dispatch/build files: formatted those and the
   subsequently edited IPC test; `ruff format --check .` passed for all 58 files.
4. An obsolete IPC test expected `report.generate` to be unimplemented. The
   implemented method correctly returns `PROJECT_NOT_FOUND` without a project;
   the updated IPC suite passed 23/23, with lint and strict types also passing.

All checks are satisfied after these targeted corrections. The full gate was not
repeated. Its original log is `.cache/phase7-quality-gate.log`.
The unique automated test total is **283 passing**: 231 Python, 33 frontend,
16 Rust and 3 repository tests. Packaged smoke scenarios are additional checks.

Windows Tauri optimized release build: PASS, producing
`apps/desktop/src-tauri/target/release/mediaqc-desktop.exe`.
Standalone engine, native lifecycle, project, job, audio and MP4/MXF video
packaged smokes: PASS. ReportLab and its embedded font worked in the packaged
runtime without separately installed end-user tools. Source bytes/mtime stayed
unchanged; focused fixtures also checked that no source-adjacent files appeared.

Clean-machine installation, firewall-enforced offline execution and manual native
UI review were not performed. No installer or Phase 8+ feature was added.
All work remains uncommitted on `phase/07-reports` for manual review.
