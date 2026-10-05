# MediaQC V1 — Master Specification

**Status:** Authoritative  
**Version:** 1.2.0

**Target:** Windows 10/11, offline-first  
**Working product name:** MediaQC

**Active phase:** Phase 12 — detector acceptance corpus and calibration framework.

**Amendment status:** Phase 12 corpus/framework implementation authorized; preserve
General Technical QC 1.2.0 and historical verdict behavior. Calibration changes
require positive and negative acceptance evidence, never reference-specific suppression.

---

## 1. Authority and precedence

This file and the documents under `specs/` define the MediaQC V1 source of truth.

If implementation and specification conflict, the specification wins until it is intentionally amended.

Precedence:

1. `MASTER_SPEC.md`
2. `AGENTS.md`
3. `specs/01_PRODUCT_SPEC.md` through `specs/10_WINDOWS_BUILD.md`
4. Tests derived from those specifications
5. Implementation

An AI coding agent MUST NOT silently reinterpret a requirement to make implementation easier.

---

## 2. V1 mission

MediaQC V1 is a **desktop technical media quality-control application**.

A user SHALL be able to install MediaQC on a clean Windows 10/11 computer, select local audio/video media, choose a QC profile, run an offline analysis, review timestamped findings with evidence, and export a report.

Core analysis SHALL NOT require internet connectivity.

The application SHALL NOT modify the source media.

---

## 3. Primary operating model

```text
User
  |
  v
Tauri Desktop Shell
  |
  v
React/TypeScript UI
  |
  v
Tauri Process Controller
  |
  | line-delimited JSON RPC over stdin/stdout
  v
Bundled Local QC Engine
  |
  +-- Media inspection: ffprobe
  +-- Decode / measurement: FFmpeg
  +-- Audio DSP: Python + NumPy/SciPy
  +-- Video CV: Python + OpenCV
  +-- QC rule evaluation
  +-- Evidence generation
  +-- SQLite persistence
  |
  v
Findings / Evidence / Reports
```

No local HTTP server is required for V1.

---

## 4. Technology decisions

V1 baseline:

| Layer | Decision |
|---|---|
| Desktop shell | Tauri |
| UI | React + TypeScript |
| Styling | Tailwind CSS or equivalent utility CSS |
| Local engine | Python 3.12-compatible codebase |
| Engine packaging | Standalone Windows executable/runtime |
| Media tools | Bundled `ffmpeg.exe` and `ffprobe.exe` |
| Audio numerical work | NumPy + SciPy |
| Video computer vision | OpenCV |
| Database | SQLite |
| ORM / DB access | SQLAlchemy 2.x style or equivalent explicit repository layer |
| IPC | newline-delimited JSON messages over child-process stdin/stdout |
| Reports | local HTML + PDF |
| Cloud dependency | prohibited for core V1 |
| AI | optional; local only; never required |

Exact dependency versions SHOULD be pinned in lockfiles during implementation.

---

## 5. Global non-goals

V1 MUST NOT:

- modify, normalize, repair, re-encode, denoise, recolor, or overwrite source media;
- require an OpenAI, Anthropic, Google, Microsoft, or other cloud account;
- require a backend server, Redis, PostgreSQL, Celery, Kubernetes, Docker, or message broker;
- upload media or QC findings to any remote service;
- depend on an LLM for deterministic measurements;
- require Python, Node.js, npm, FFmpeg, Git, Visual Studio, or CUDA to be separately installed by the end user;
- perform copyright detection;
- perform content moderation;
- perform speaker identification;
- perform general semantic scene understanding;
- claim regulatory/broadcast compliance unless a selected QC profile explicitly defines the relevant thresholds and the implementation has tests for them.

---

## 6. V1 supported media intent

V1 SHALL support any media that bundled FFmpeg can reliably demux/decode for the implemented detectors, including common:

- MOV
- MP4
- MXF
- WAV
- AIFF
- FLAC
- MP3
- AAC

Unsupported or partially supported media SHALL fail gracefully and produce actionable error information.

This list expresses broad V1 media intent, not evidence of validation for every
extension. Phase 10 automatic folder discovery SHALL include only `.wav`, `.mp3`,
`.mp4`, and `.mxf` (case-insensitive). These are the documented, validated core
formats; see `specs/01_PRODUCT_SPEC.md` section 10. Additional extensions require
explicit documentation and validation before addition. FFmpeg capability alone
does not establish supported status. Explicit single-file selection retains its
existing unrestricted selection and probe-based validation behavior.

---

## 7. Core result model

Every analysis produces:

1. media metadata;
2. zero or more findings;
3. evidence;
4. a run summary;
5. final overall status;
6. report artifacts.

Severity enum:

```text
INFO
WARN
FAIL
```

Disposition enum:

```text
OPEN
CONFIRMED
FALSE_POSITIVE
IGNORED
```

Run status enum:

```text
QUEUED
INSPECTING
ANALYZING
GENERATING_EVIDENCE
GENERATING_REPORT
COMPLETED
CANCELLED
FAILED
```

Overall result:

- `FAIL` if one or more active FAIL findings exist.
- else `WARN` if one or more active WARN findings exist.
- else `PASS`.

INFO findings do not change overall result.

Active findings have disposition `OPEN` or `CONFIRMED`; `FALSE_POSITIVE` and
`IGNORED` do not contribute, consistent with the product acceptance examples.
Only `COMPLETED` analyses receive PASS/WARN/FAIL. Incomplete, failed, and cancelled
runs retain a null verdict. Batch item `ERROR` is an execution outcome, not QC
severity `FAIL`. Batch completion does not assert that all files passed.

---

## 8. Canonical detector IDs

### Audio

- `audio.loudness.integrated`
- `audio.loudness.short_term`
- `audio.loudness.momentary`
- `audio.loudness.range`
- `audio.true_peak`
- `audio.sample_peak`
- `audio.clipping`
- `audio.silence`
- `audio.noise_floor`
- `audio.hum`
- `audio.channel_imbalance`
- `audio.phase_correlation`
- `audio.dropout`
- `audio.discontinuity`

### Video

- `video.decode_integrity`
- `video.frame_rate`
- `video.timestamp_integrity`
- `video.black_frame`
- `video.near_black_frame`
- `video.freeze`
- `video.duplicate_frame`
- `video.frame_cadence`
- `video.luminance_anomaly`
- `video.flash`
- `video.exposure_anomaly`
- `video.color_anomaly`
- `video.visual_anomaly`

Detector behavior and schemas are specified in `specs/04_DETECTOR_SPEC.md`.

---

## 9. QC profiles

All thresholds MUST be defined outside detector code.

A detector MAY define algorithmic constants required for implementation, but any value that represents a user/business QC policy MUST live in the selected QC profile.

Each profile SHALL have:

- stable ID;
- human-readable name;
- semantic version;
- description;
- detector enable/disable settings;
- thresholds;
- severity mapping;
- creation/update metadata.

See `specs/05_QC_PROFILE_SPEC.md`.

---

## 10. Project filesystem model

Default project layout:

```text
<Project Directory>/
  project.sqlite
  evidence/
    audio/
    video/
    thumbnails/
  reports/
  cache/
  logs/
```

The source media file SHALL remain at its original location.

The project database stores its absolute path plus metadata sufficient to warn when the file changes or moves.

Large media SHALL be processed as streams/chunks. Entire media files MUST NOT be loaded into RAM.

---

## 11. Build phases

AI coding agents SHALL implement in this order unless the spec is amended.

### Phase 0 — Repository and quality gates

Deliver:

- repository structure;
- linting/formatting;
- TypeScript checks;
- Python lint/type/test configuration;
- CI-capable test commands;
- spec files copied into repository;
- `AGENTS.md` acknowledged by implementation notes.

Exit criteria:

- empty shell builds;
- test commands run;
- no QC logic yet.

### Phase 1 — Desktop shell + engine IPC

Deliver:

- Tauri app;
- React shell;
- engine executable launched as managed child process;
- JSON-line IPC;
- ping/version/capabilities methods;
- clean engine shutdown;
- user-visible engine error handling.

Exit criteria:

- UI can launch engine;
- UI can send `system.ping`;
- engine responds using exact IPC envelope.

### Phase 2 — Projects + SQLite + media inspection

Deliver:

- create/open project;
- schema/migrations;
- file chooser;
- ffprobe metadata ingestion;
- media/stream persistence;
- source-file fingerprint;
- inspection UI.

Exit criteria:

- project reopens across app restart;
- supported test media metadata matches expectations;
- unsupported file shows error without crashing.

### Phase 3 — Job orchestration

Deliver:

- local job manager;
- start/cancel/retry;
- progress events;
- detector scheduling;
- persistent run state;
- crash recovery rule.

Exit criteria:

- run can be cancelled;
- UI remains responsive;
- engine does not orphan child FFmpeg processes.

### Phase 4 — Deterministic audio QC

Implement and test, in order:

1. loudness metrics;
2. true/sample peak;
3. clipping;
4. silence;
5. channel imbalance;
6. phase correlation;
7. hum;
8. noise floor;
9. dropout/discontinuity.

Exit criteria:

- synthetic fixtures pass tolerance windows in testing spec.

### Phase 5 — Deterministic video QC

Implement and test, in order:

1. decode integrity;
2. frame-rate/timestamp integrity;
3. black/near-black;
4. freeze;
5. duplicate/cadence;
6. luminance/flash;
7. exposure/color anomaly;
8. conservative generic visual anomaly.

Exit criteria:

- synthetic fixtures pass;
- clean corpus false-positive budget is met.

### Phase 6 — Evidence + results UX

Deliver:

- finding list;
- timeline;
- issue inspector;
- still-frame evidence;
- before/current/after video frame evidence;
- waveform/spectrogram evidence;
- disposition controls.

Exit criteria:

- each FAIL/WARN finding can be inspected;
- missing evidence is explicit, never silently ignored.

### Phase 7 — Reports

Deliver:

- HTML report;
- PDF report;
- run/profile version included;
- disposition-aware summary.

Exit criteria:

- report reproducible from saved project/run;
- report can be generated without internet.

### Phase 8 — Optional local AI

Deliver only after deterministic QC is stable:

- local AI feature flag;
- local model availability check;
- structured AI review;
- evidence-only input;
- no AI override of raw measurement.

Exit criteria:

- app works identically with AI disabled;
- AI failure cannot fail deterministic analysis.

### Phase 9 — Windows packaging/performance

Deliver:

- signed-ready installer configuration;
- bundled engine;
- bundled FFmpeg/ffprobe;
- clean-machine installation test;
- uninstall test;
- CPU-only test;
- offline test;
- large-file test.

---

### Phase 10 — Batch processing + streamlined operator UX

Deliver:

- persistent engine-owned batches and queue items in SQLite schema version 3;
- asynchronous folder discovery under the section 6 format restriction;
- exactly one active media file per engine, including inspection and evidence;
- Pause after the current file, Resume pending work, and safe Stop;
- retained completed results and explicit continuation of pending files after
  unexpected termination, without mid-file resume;
- compact SQLite-filtered, paginated dashboard (50 rows per page);
- selected-file drill-down, deterministic measured-versus-threshold explanations,
  and collapsed Technical details;
- existing per-run HTML/PDF reports plus compact batch HTML/PDF summaries;
- installer and portable offline acceptance coverage.

Exit criteria are the Phase 10 matrix in `specs/09_TESTING_SPEC.md`. Preserve all
existing detector mathematics, profile thresholds, verdict/disposition semantics,
evidence, notes, local optional AI, source immutability, subprocess ownership, and
bounded-memory guarantees. No parallel files, production AI model/runtime,
automatic restart, mid-file checkpoints, watch folders, or new runtime services
are introduced. Queue entries SHALL NOT pre-create queued analysis runs.

---

### Phase 11 — Performance preservation baseline

The completed performance work is recorded in `docs/PHASE_10_PERFORMANCE_FIX.md`.
Preserve shared bounded PCM reuse, vectorized dropout windows, bounded decoder
threading, R128 reuse, source immutability, cancellation and terminal cleanup.

### Phase 12 — Detector calibration and reference corpus

Build the acceptance framework before changing detector algorithms. Separate
measurement correctness, selected-profile compliance and technical-defect intent.
Keep General Technical QC 1.2.0 unchanged; introduce no new technical-only profile.
Use reproducible small synthetic positive/negative fixtures and local-only reviewed
references. Normal zoom, auto-exposure, cuts, focus adaptation and natural motion
are negative technical-defect cases. Retain deliberate corruption/freeze/repeat
positives. Unknown transient intent remains unresolved, never presumed clean.
Explicit runtime audio assignments are now authorized for new runs under the
versioned explicit_audio_v1 applicability policy. Unassigned runs preserve legacy
behavior; historical results are never rewritten. See the Phase 12 runtime
addenda in database, detector, profile and IPC specifications. No new
detectors (including dedicated dead/stuck-pixel detection) are implied by corpus
examples. Record unimplemented coverage explicitly.

Use focused validation during development. Full gates, builds and packaging are
reserved until implementation is stable. Do not commit, push, merge or open a PR
without further user instruction. See `specs/09_TESTING_SPEC.md` section 20.

---

## 12. Global acceptance criteria

V1 is complete only when ALL of the following are true:

- App installs on a clean Windows 10/11 machine without developer tooling.
- App launches with internet disconnected.
- App performs core QC with outbound network blocked.
- Source media is never modified.
- Projects persist and reopen.
- User can choose a QC profile.
- Audio and video detector suites produce structured findings.
- Every WARN/FAIL contains detector ID, timestamps when applicable, severity, measurements, profile context, and evidence or an explicit evidence-generation error.
- User can mark a finding confirmed, false positive, or ignored.
- Overall result updates according to disposition rules.
- User can export HTML and PDF.
- App survives corrupt/unsupported media without process crash.
- Cancelling a run terminates related worker/FFmpeg processes.
- No required threshold is hard-coded in UI or detector implementation.
- Synthetic regression corpus passes.
- Clean corpus stays within defined false-positive budgets.
- AI can be entirely disabled.
- Windows installer bundles required runtime dependencies.
- No core V1 workflow requires account sign-in or cloud services.
- Phase 10 batch acceptance passes with AI OFF in installed and portable builds.

---

## 13. Performance objectives

These are objectives, not hard guarantees across all hardware/codecs:

- Metadata inspection SHOULD begin showing results within seconds on normal local media.
- CPU-only 1080p QC SHOULD target at least real-time or faster for the common deterministic detector set where codec complexity allows.
- 4K analysis SHALL support configurable sampling/quality strategy rather than exhausting memory.
- Memory usage SHALL remain bounded by chunk/window size rather than source duration/file size.
- UI event loop MUST remain responsive during analysis.

Performance work MUST NOT reduce detector correctness without an explicit quality-mode/profile setting.

---

## 14. Change-control rule

Any proposal that changes one of these requires a specification update before implementation:

- IPC transport;
- database technology;
- detector IDs;
- finding schema;
- profile schema;
- source-media immutability;
- offline requirement;
- core language/runtime split;
- severity/disposition semantics;
- project directory structure;
- Windows-first packaging approach.

---

## 15. Coding-agent execution prompt

Historical Phase 0 bootstrap prompt (not the active-phase instruction):

```text
You are implementing MediaQC V1.

Read MASTER_SPEC.md, AGENTS.md, and every file under specs/ before writing code.

The specifications are authoritative. Do not invent alternative architecture.
Do not add cloud dependencies or a local web server.
Do not modify source media.
Do not implement later phases early.

Start with Phase 0 only.
Before coding, summarize:
1. repository structure you will create,
2. commands used for lint/test/build,
3. assumptions that are not already specified.

Then implement Phase 0 and run its acceptance checks.
Do not proceed to Phase 1 until Phase 0 is complete.
```

For Phase 10, read the approved amended specifications and implement only after
explicit implementation approval. Specification approval alone does not authorize
application changes, dependency installation, full quality gates, or packaging.

### Approved Phase 12 V1 acceptance disposition

The approved two-result acceptance model in specs/09_TESTING_SPEC.md section 21
separates unchanged ground-truth mismatches from narrowly accepted release
limitations. The twelve enumerated exceptions and unresolved reference status do
not change production signal processing, General Technical QC 1.2.0, historical
results or required recall outside those explicit entries. Final validation remains
separately authorized; approval of limitations is not Phase 12 completion.
