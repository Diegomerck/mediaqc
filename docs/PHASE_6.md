# Phase 6 — Evidence and results UX

Phase 6 extends the Phase 0–5 Tauri / React / local Python / SQLite architecture.
No dependencies, database migration, detector policy changes, reports, AI, or
installer/performance work were introduced. Source media is opened for reading;
outputs remain inside the existing project filesystem.

## Results and review

The results dashboard includes saved overall status, active severity counts,
disposition counts, media filename, run date, and immutable profile context.
Audio/video detector groups retain execution status, finding counts, measurements,
and worst active severity. Every finding can be selected in the table and inspected.
The inspector exposes detector ID/version, stream, severity, interval/duration,
confidence, description, measurements, effective thresholds, evidence, and notes.

The list loads existing IPC pages of at most 100 findings. Severity, detector,
disposition, audio/video, and text filters explicitly operate on loaded findings;
“Load more findings” exposes remaining pages. The timeline uses the saved media
duration, zoom/pan, ranges, severity text and colors, and selection navigation.
At most 80 timeline targets are rendered; expanded clusters use 50-item pages.
Whole-program findings with null timestamps remain selectable in the list.
Native buttons, labeled controls, text severity, image descriptions, and visible
focus outlines preserve basic keyboard accessibility.

Confirm, Mark False Positive, Ignore, and Reopen save through the documented
`finding.set_disposition` method. A SQLite transaction appends operator feedback,
updates the finding, and recalculates completed-run status. `OPEN`/`CONFIRMED`
contribute; `FALSE_POSITIVE`/`IGNORED` do not. This follows the explicit examples
in `specs/01_PRODUCT_SPEC.md` section 8 and preserves Phase 5 aggregation.
Incomplete/failed/cancelled runs retain null overall status. Raw measurements and
profile snapshots remain unchanged. Notes/history survive project and engine reopen.

## Evidence generation and loading

The worker enters the specified `GENERATING_EVIDENCE` stage before completion.
The existing owned FFmpeg process runner uses the run cancellation token and a
30-second timeout per extraction. Failure of one visual artifact is recorded with
its type, error code/message, and available diagnostic excerpt in finding metadata;
other safe work continues. Cancellation propagates to the run and terminates owned
processes. No UI analysis or media playback was added.

- Video: project-local PNG current/before/after frames, downscaled within 480×270.
  Seek positions are the finding start, 0.25 seconds before start, and 0.25 seconds
  after end. Displayed evidence times are requested media seek positions; detector
  timestamps remain the authoritative finding interval. At media boundaries,
  unavailable context is an explicit error rather than a duplicated placeholder.
- Audio: project-local 640×180 waveform and spectrogram PNGs. The preview starts
  up to one second before the finding and decodes at most eight seconds, using a
  labeled mono 16 kHz preview. It is a context excerpt, not a full-program plot.
  The UI includes a time ruler and highlighted finding region. Full detector
  measurements and original finding timestamps remain available separately.
- Existing `METRICS_JSON` references and legacy projects remain readable. Old
  findings without visual evidence explicitly instruct the user to rerun analysis;
  historical runs are not modified or discarded by opening them.

`evidence.read` is documented in `specs/06_IPC_SPEC.md` and allowed by the native
controller. It accepts only an evidence ID, confines resolved paths to project
`evidence/`, validates source identity and saved image digest, and reads at most
256 KiB per artifact. PNG data travels through existing stdio IPC as a bounded
base64 data URL; the existing CSP already permits data images. No HTTP server,
asset server, remote access, arbitrary file-read method, or source upload is used.
Missing, failed, unreadable, stale, oversized, invalid, and browser image-decoding
failures are visible beside the inspector. Measurements remain inspectable.

## Verification

Focused engine tests in `engine/tests/test_evidence.py` cover real frame/waveform/
spectrogram extraction, Unicode/spaced paths, artifact limits and path confinement,
source/artifact staleness, missing evidence, generation errors, disposition
precedence, notes/history across reopen, and real FFmpeg cancellation/cleanup.
Every evidence integration fixture checks source SHA-256, mtime, and sibling files.
The existing job lifecycle test now expects the required evidence stage.

Frontend `Results.test.tsx` covers list selection/filtering, inspector/profile
context, timeline mapping/zoom/pan/clustering, all visual evidence kinds, explicit
errors, and saved disposition/status refresh. Existing results tests remain.

The complete `npm run check` workflow retains all 22 gates. Existing Phase 4/5
packaged smokes now also load each visual evidence type through the production
Windows controller and persist dispositions/notes across engine restart. These
smokes retain empty end-user PATH/PYTHONPATH and source hash/mtime assertions.

Clean Windows installation, firewall-blocked networking, and manual native
screen-reader/visual review are not established by these automated checks.
Installer and full platform-matrix validation remain Phase 9. Phase 6 does not
implement Phase 7 reports or Phase 8 AI.

## Recorded validation — 2026-09-19

Phase 6 exit criteria:

- PASS: every FAIL/WARN can be selected and inspected, including paginated and
  whole-program findings.
- PASS: absent, failed, missing, stale, or unreadable evidence is explicit;
  measurements remain available.

New focused Phase 6 coverage: **45 tests passed** (32 engine + 13 frontend).
The focused frontend command also ran four existing results regressions: 17/17.
The evidence/job combined run passed 48/49 initially; its one Phase 5 lifecycle
expectation was updated to include `GENERATING_EVIDENCE`, then passed alone.

The full `npm run check` was executed **once**, with all 22 gates attempted.
It initially reported 20 PASS and two failures:

1. `format:check`: eight pre-existing Phase 5 files needed Prettier formatting.
   Formatting-only changes were applied; `npm run format:check` then passed.
   Parsed JSON equality confirmed unchanged profiles, dependencies/scripts,
   and fixture expectations.
2. `python:test`: 219/220 passed. The remaining Phase 5 test mocked only metrics
   JSON writes but expected an empty evidence list. Its assertion now requires
   the three independently successful Phase 6 frame artifacts on disk and still
   requires the original `EVIDENCE_WRITE_FAILED` diagnostic. The targeted test
   passed; Python lint, formatting and strict types passed for the update.

All checks are satisfied after those targeted corrections; the complete gate
was not repeated. The original full-run log is `.cache/phase6-quality-gate.log`.
Unique automated test totals across the full run and corrected targeted reruns:
**269 passing** = 220 Python + 30 frontend + 16 Rust + 3 repository tests.

Windows Tauri optimized release build: PASS, producing
`apps/desktop/src-tauri/target/release/mediaqc-desktop.exe`.
Packaged smokes: PASS for standalone engine (10,000 messages), native process
lifecycle, project/inspection, jobs, audio, and MP4/MXF video. The audio and both
video smokes exercised Phase 6 evidence loading and disposition/note persistence
across restart. Source SHA-256/mtime remained unchanged; integration fixtures also
confirmed no source-adjacent sidecars. Installer creation was not performed.

Principal commands used (with the repository's existing uv/Rust cache paths):

```powershell
.venv/Scripts/python.exe -m pytest engine/tests/test_evidence.py engine/tests/test_jobs.py -q
.venv/Scripts/python.exe -m pytest engine/tests/test_evidence.py -q
npm test --workspace @mediaqc/frontend -- --run tests/Results.test.tsx tests/AudioResults.test.tsx
npm run check
npm run format:check
.venv/Scripts/python.exe -m pytest engine/tests/test_video.py::test_disabled_video_detector_and_evidence_write_failure -q
.venv/Scripts/python.exe -m pytest engine/tests/test_jobs.py::test_complete_progress_snapshot_and_sequential_runs -q
.venv/Scripts/python.exe -m mypy
git diff --check
```

Changes are intentionally uncommitted on `phase/06-evidence-results-ux`.
No Phase 7+ functionality was implemented.
