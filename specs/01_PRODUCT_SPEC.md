# 01 — Product Specification

**Version:** 1.1.0

## 1. Problem statement

Professional media can contain technical defects that are tedious to locate manually. MediaQC V1 provides deterministic offline analysis of local media and presents timestamped, evidence-backed findings.

It is a QC assistant, not an autonomous creative or compliance authority.

## 2. Personas

### QC Operator
Needs fast technical review, evidence, timestamps, and a printable report.

### Editor / Post Supervisor
Needs to find likely technical problems before delivery.

### Production Technician
Needs offline use on media workstations with restricted/no internet access.

## 3. Primary workflow

1. Launch MediaQC.
2. Create/open project.
3. Select Media / Folder; review the imported queue and exclusions.
4. Select QC profile and optional AI mode (OFF by default).
5. Choose Run QC Analysis.
6. Inspect each selected file automatically immediately before its QC turn.
7. Observe batch progress; Pause, Resume, or Stop as needed.
8. Review compact batch results and select a file for details.
9. Inspect findings on timeline.
10. Confirm / mark false positive / ignore.
11. Export HTML/PDF report.
12. Reopen project later and reproduce run context.

## 4. Functional requirements

### PRD-001 Offline core
Core workflow SHALL work with all outbound network access blocked.

### PRD-002 Source immutability
MediaQC SHALL not alter source media bytes or metadata.

### PRD-003 Project persistence
Projects SHALL persist in a local project directory with SQLite and evidence folders.

### PRD-004 Media inspection
MediaQC SHALL display at minimum:

- file name/path;
- size;
- modification time;
- duration;
- container;
- video codec/resolution/frame-rate data;
- audio codec/sample rate/channel count/layout when available;
- stream count.

### PRD-005 QC profile selection
A run SHALL capture the exact profile ID/version/snapshot used.

### PRD-006 Structured findings
Each finding SHALL expose:

- detector ID/version;
- severity;
- stream;
- start/end time if applicable;
- title/description;
- measurements;
- configured threshold/context;
- confidence where meaningful;
- evidence references;
- disposition.

### PRD-007 Overall result
PASS/WARN/FAIL SHALL follow the master-spec severity/disposition rule.

### PRD-008 Evidence
WARN/FAIL findings SHOULD include evidence. If evidence creation fails, the finding remains valid and the evidence failure is recorded.

### PRD-009 Human disposition
Operator SHALL be able to mark findings:

- OPEN;
- CONFIRMED;
- FALSE_POSITIVE;
- IGNORED.

### PRD-010 Reports
A completed run SHALL support local HTML and PDF export.

### PRD-011 Cancellation
A running analysis SHALL be cancellable.

### PRD-012 Diagnostics
The application SHALL expose a way to open local diagnostic logs.

## 5. Detector scope

### Audio required V1
- loudness metrics;
- true/sample peak;
- clipping;
- silence;
- noise floor;
- hum;
- channel imbalance;
- phase correlation;
- dropout/discontinuity.

### Video required V1
- decode integrity;
- frame rate;
- timestamp integrity;
- black/near-black;
- freeze;
- duplicate frame/cadence;
- luminance/flash;
- exposure/color anomaly;
- conservative visual anomaly candidates.

## 6. Explicit non-goals

V1 does not promise:

- final broadcaster acceptance certification;
- creative intent interpretation;
- repair;
- transcription;
- speaker identification;
- subtitle/caption QC;
- lip-sync measurement;
- HDR mastering validation;
- IMF package validation;
- Dolby-specific compliance;
- reference-based perceptual quality scoring;
- distributed rendering.

These may be later versions.

## 7. Product UX principles

- Technical but understandable.
- Always show why a finding exists.
- Prefer evidence over opaque scores.
- Never hide deterministic measurements behind AI prose.
- Conservative defaults are better than overwhelming false positives.
- Every irreversible action requires explicit user intent; V1 has almost none.
- Source media location is visible and never silently copied.

## 8. Overall result acceptance tests

Given findings:

```text
INFO open
WARN false_positive
FAIL ignored
```

Overall result SHALL be PASS.

Given:

```text
WARN confirmed
```

Overall result SHALL be WARN.

Given:

```text
FAIL open
WARN open
```

Overall result SHALL be FAIL.

## 9. V1 completion statement

MediaQC V1 is complete when a non-developer can install it on Windows, analyze supported local media offline, understand the detected issues with evidence, disposition findings, and export a reproducible report.

## 10. Phase 10 batch requirements

### PRD-013 Import policy

- A batch belongs to one project. Select one source folder or one explicit file;
  single-file operation is a one-item batch in the new UI. Existing single-run
  APIs and historical results remain usable.
- Automatic folder extensions are exactly `.wav`, `.mp3`, `.mp4`, `.mxf`, matched
  case-insensitively. Existing validation includes WAV project/audio tests,
  MP4/MXF video tests, and WAV/MP3/MP4/MXF release validation recorded in
  `docs/PHASE_9.md` and `tools/smoke_release.py`. AAC audio inside an MP4 does not
  validate standalone `.aac`. MOV/AIFF/AIF/FLAC/AAC are not added to discovery.
- Explicit file selection retains unrestricted selection and actual ffprobe/
  detector support checks. Extension eligibility never guarantees successful QC.
- Include subfolders is optional and OFF by default. Discovery never follows
  symbolic links, directory junctions, or other reparse-point entries, including
  a selected folder that is itself such an entry. Report exclusions explicitly.
- Deduplicate normalized absolute paths within a batch using Windows path
  normalization/case handling; preserve the original display path. Do not hash
  contents for deduplication. Different paths, including hard links, remain
  distinct. New batches may reference previously analyzed sources.
- Persist discovered candidates without decoding them. Capture size/mtime when
  available. Sort by normalized relative path (absolute path for explicit input),
  with a stable tie-breaker, and freeze membership/order when discovery completes.
- Exclude unsupported extensions and engine-owned DB/cache/evidence/report/log
  artifacts. Persist inspectable exclusion reasons and counts outside queue totals.
  Record unreadable subdirectories as import problems; make partial discovery
  prominent. An unreadable root fails discovery. Never silently claim a complete
  scan after a directory-access error.
- A supported candidate that cannot be read remains a queue member and becomes
  `ERROR` when processed. Corrupt/unreadable/changed/missing media must not stop
  other safe work. Preserve structured errors and available diagnostic references.
- Changed import size/mtime or inspection fingerprint produces `MEDIA_CHANGED`
  rather than silently analyzing changed content. Reimport is an explicit action.
- No candidates means Run QC Analysis is disabled. Discovery is cancellable and
  must not block control requests. No source bytes, metadata, names, or locations
  are modified, and no source-adjacent sidecars are created.

### PRD-014 Queue and controls

Exactly one file is active per engine, from inspection through analysis, evidence,
and optional advisory work. Freeze the selected valid profile snapshot and AI mode
at batch start; Resume uses that snapshot. Completed run history is immutable
except for existing explicit operator dispositions/notes.

Pause finishes the current file and prevents the next from starting; show
"Pausing after current file..." until paused. Resume continues pending files.
Stop blocks scheduling, cancels active inspection/analysis, and marks pending
items `CANCELLED`; completed results are preserved. Stop is not Resume. Failed or
cancelled files can be retried as a new batch, retaining original batch/run links.
Detailed transitions and recovery rules are authoritative in `02_ARCHITECTURE.md`.

### PRD-015 Review and persistence

Persist batch membership, order, settings, state, completed run links, and errors.
Reopen previous batches without rerunning media. After unexpected termination,
reconcile persisted state and offer "Continue pending files" explicitly; never
automatically restart or resume inside a file. An interrupted discovery is not a
complete batch and requires a new import.

The dashboard SHALL distinguish PASS/WARN/FAIL from ERROR/CANCELLED and show total,
processed, processing, and pending counts. Only completed QC contributes a verdict.
Needs attention includes WARN, FAIL, and ERROR. Use SQLite filters and 50-row pages.
Load detailed run data only for the selected file and evidence only for the selected
finding. Preserve all diagnostic information behind collapsed Technical details.

Measured-versus-threshold explanations are deterministic engine presentation of
saved measurements and saved policy, never AI evaluation or new QC calculations.
No new thresholds, severities, or detector results may be introduced by wording.

### PRD-016 Batch reports

Keep existing detailed per-run HTML/PDF reports. Add batch HTML/PDF summaries with
batch name, profile/version, generation time, queue state, totals, verdict/error
counts, and one compact row per processing member (relative path, execution state,
verdict or no verdict, active issue counts, and concise error where relevant).
Summarize exclusions/import problems separately; do not embed every evidence item.
Allow export only when PAUSED or terminal (including INTERRUPTED); label incomplete
or stopped work explicitly. Save consistent snapshots under project `reports/`,
retain older exports, and record the batch revision. Report generation does not
require source media or a production AI provider; detailed report safeguards remain.
