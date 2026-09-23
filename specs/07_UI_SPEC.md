# 07 — UI Specification

**Version:** 1.1.0

## 1. UX goals

- Desktop-native workflow.
- Dark/high-contrast friendly.
- Clear status hierarchy.
- Technical values accessible without overwhelming first view.
- Evidence one click away from finding.
- No cloud/account concepts in core V1.

## 2. Navigation

Required sections:

1. Projects
2. Project Overview
3. Select Media / Folder
4. Batch Dashboard / Analysis Progress
5. File Results
6. Finding Inspector
7. QC Profiles
8. Settings / Diagnostics

## 3. Projects screen

Required:

- create project;
- open existing project;
- recent projects;
- last run result/status;
- last opened date.

Empty state clearly explains local project folders.

## 4. Project overview

Show:

- project name/path;
- media assets;
- previous runs;
- profile used;
- result;
- report shortcuts.

Source media path must be visible.

If source file missing/changed, show warning.

## 5. New analysis

Required fields:

- media selection;
- profile selection;
- AI mode (`OFF` required; `LOCAL` only if capability exists);
- project/output context.

Before enabling Run QC Analysis:

- batch discovery complete with at least one candidate; inspect each file
  successfully before its analysis starts, not before enabling the batch button;
- profile valid;
- no active conflicting run.

The legacy explicit inspection/single-run API retains its successful-inspection
prerequisite. Inspection is automatic inside the new batch workflow.

## 6. Selected-file progress screen

Show:

- filename;
- overall progress;
- stage;
- current detector;
- media position / duration when available;
- elapsed time;
- detector checklist;
- Cancel button.

For batch-owned files use batch Stop instead of independent Cancel. Current detector
and checklist belong in collapsed Technical details. Section 19 defines the primary
batch progress screen.

Estimated remaining time MAY be shown but must be labeled estimate.

No fake smooth progress; use actual engine events.

## 7. Results dashboard

Header:

- overall PASS/WARN/FAIL;
- counts by severity;
- counts by disposition;
- media filename;
- profile name/version;
- run date/time.

Detector groups (inside collapsed Technical details for the selected file):

- Audio
- Video

Each detector displays:
- completion status;
- finding count;
- worst active severity.

## 8. Findings table/list

Columns:

- severity;
- time;
- detector;
- title;
- duration;
- confidence where applicable;
- disposition.

Filters:

- severity;
- detector;
- disposition;
- audio/video;
- search text.

Click opens inspector and positions timeline.

## 9. Timeline

Required:

- horizontal time axis;
- finding markers/ranges;
- severity visually distinguishable;
- zoom/pan;
- click finding to inspect.

Timeline MUST remain useful for long-form content.

Markers should cluster or virtualize rather than render thousands of DOM elements if necessary.

## 10. Finding inspector

All fields below remain accessible. Technical identity/raw metadata belong in
collapsed Technical details; human-readable measurements and thresholds remain visible.

Required fields:

- severity;
- title;
- detector ID/version;
- stream;
- start/end/duration;
- confidence;
- description;
- measurements;
- thresholds/profile values;
- evidence;
- disposition controls;
- optional note.

Evidence views:

### Audio
- waveform;
- spectrogram;
- time ruler;
- finding region.

### Video
- frame before;
- issue frame;
- frame after;
- timestamp.

V1 does not require media playback, though it MAY be added if it does not jeopardize schedule.

## 11. Disposition controls

Buttons/actions:

- Confirm
- Mark False Positive
- Ignore
- Reopen

Changing disposition updates overall result immediately based on saved data.

## 12. QC profile screen

Required:

- list profiles;
- view profile JSON-derived form;
- enable/disable detector;
- edit allowed thresholds;
- validation errors;
- duplicate built-in into user profile.

Advanced raw JSON editor MAY be offered behind an advanced mode.

## 13. Settings

Required:

### General
- default project directory;
- temp/cache directory;
- evidence retention preference if implemented.

### Performance
- analysis quality: `FAST`, `BALANCED`, `THOROUGH`;
- worker/concurrency setting if exposed.

### AI
- `OFF`;
- `LOCAL` if supported;
- local model status.

### Diagnostics
- engine version;
- FFmpeg version;
- protocol version;
- database schema version;
- open logs folder.

## 14. Accessibility

- Keyboard navigation for core controls.
- Sufficient contrast.
- Do not communicate severity by color alone.
- Use icons/text labels.
- Focus states visible.
- Avoid tiny timestamp targets.

## 15. Error UX

Errors must contain:

- what failed;
- whether analysis can continue;
- a short user action;
- diagnostic code;
- optional "Open logs" action.

Example:

```text
Media inspection failed
The file could not be decoded by the bundled media engine.

Code: MEDIA_INSPECTION_FAILED

[Open logs] [Choose another file]
```

## 16. Source media safety UX

Do not show actions labeled:
- Fix;
- Repair;
- Normalize;
- Replace original.

V1 report/evidence output destinations are separate from source media.

## 17. UI acceptance criteria

- User can finish primary workflow without opening developer console.
- All terminal run states have clear visuals.
- Finding inspector shows raw measurement + threshold.
- Offline mode produces no missing-cloud UX.
- Unsupported media error does not lose project state.
- UI stays responsive during full analysis.

## 18. Phase 8 local AI controls

The analysis form exposes OFF (default), capability-gated LOCAL, and current local
model status. The same status supports AI diagnostics; mode is per run, not a
global persisted default. The inspector displays saved advisory review text,
classification/confidence, recommendation, model/template identity, UTC creation
time and evidence references. Missing/failed reviews are explicit. OFF leaves
the deterministic results view unchanged. Operator disposition remains manual.

## 19. Phase 10 compact operator workflow

Present **Select Media / Folder → Run QC Analysis → Review Results**. Separate
project/output location from sources. Use compact project reads and paginated batch
history; do not expand every asset, stream, run, detector, or finding. Existing
standalone runs remain accessible through paginated history. The batch continues
while the operator reviews a completed file.

Selection offers File and Folder, batch name (default folder name/file stem), profile,
and AI mode (OFF default; LOCAL capability-gated). Include subfolders is visibly OFF.
Advertise only WAV/MP3/MP4/MXF for folder discovery. Show discovery status, candidates,
excluded/duplicate counts, and a paginated import summary. Identify incomplete
directory access and zero-candidate imports prominently. Starting a batch does not
claim every candidate has already passed inspection.

### Batch dashboard

```text
Batch: Delivery_20_Sep       Profile: General Technical QC
38 of 137 processed        Overall: approximately 28% (file-weighted)
Current: EP04_SC039_FINAL.mxf       File progress: 73%
[Pause] [Stop]
PASS 31   WARN 5   FAIL 2   ERROR 0
PROCESSING 1   PENDING 98   CANCELLED 0
All | Needs attention | Fail | Warn | Pass | Other states
PASS  EP04_SC001_FINAL.mxf
WARN  EP04_SC003_FINAL.mxf
FAIL  EP04_SC004_FINAL.mxf
Previous                 Page 1                 Next
```

Use 50 rows/page and SQLite filtering/totals across the entire batch. Mount only
the visible batch page, with no expanded results/evidence prefetch for other files.
Use relative paths to distinguish duplicate basenames; absolute paths remain
accessible. Clicking a row opens that file only. ERROR/CANCELLED and no verdict are
distinct from FAIL/PASS. Needs attention includes WARN/FAIL/ERROR; other-state filters
expose pending/processing/cancelled. Exclusions never inflate queue totals.

Show "Pausing after current file..." in PAUSING, Resume in PAUSED, and "Stopping..."
until cleanup completes. Keep Stop usable during inspection, analysis, and pausing.
Disable conflicting starts and report exports. Preserve page/filter on return from
drill-down. Announce state changes without flooding screen readers with progress ticks.

Overall progress is the engine's file-weighted estimate; processed excludes
cancelled work. Unknown progress is indeterminate. Completed with errors and stopped
batches are explicit. On eligible INTERRUPTED batches offer "Continue pending files"
with saved settings and show the interrupted file as Error. Interrupted discovery
instead offers reimport. Retry unsuccessful files creates a new batch, retaining history.

### File and finding drill-down

Lead with filename, verdict (or execution error), active warning/failure counts,
profile name/version, and understandable finding titles. Example:

```text
WARN — 1 warning found
Integrated loudness is below the accepted range.
Measured: -24.12 LUFS
Target: -23 LUFS ±1 LU
Accepted range: -24.0 to -22.0 LUFS
Difference from limit: 0.12 LU
```

These are example saved values, not a new profile default. Do not invent policy
categories such as "slightly". Render deterministic engine explanations; React does
not derive DSP measurements or reinterpret severity. Display precision must reveal
boundary violations rather than rounding them into range. Unknown schemas retain
saved descriptions and labeled measurements.

Keep finding selection, timeline, evidence, dispositions, and notes. Load evidence
only for the selected finding and release prior previews on selection changes.
Missing/stale evidence and execution errors remain visible outside Technical details.
Ignored/false-positive findings remain accessible through existing filters. Saving a
disposition refreshes the file verdict and affected batch counts/filter.

One explicit Technical details section is collapsed by default: detector IDs/versions,
UUIDs, skipped detectors, full metrics, raw JSON, profile JSON, internal evidence
metadata, and reproducibility diagnostics. Retain every record. Human-readable
measurements/thresholds remain visible without expanding this section. AI advice stays
separate and labeled advisory; it never supplies these explanations. No production
model/runtime is introduced.

Keep detailed per-run HTML/PDF export in file results. Offer compact batch HTML/PDF
when paused or terminal and no other batch is active; label partial exports and
retain previous artifacts.
