# 07 — UI Specification

**Version:** 1.0.0

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
3. New Analysis / Media
4. Analysis Progress
5. Results
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

Before enabling Analyze:
- media inspection successful;
- profile valid;
- no active conflicting run.

## 6. Progress screen

Show:

- filename;
- overall progress;
- stage;
- current detector;
- media position / duration when available;
- elapsed time;
- detector checklist;
- Cancel button.

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

Detector groups:

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
