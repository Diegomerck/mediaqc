# 01 — Product Specification

**Version:** 1.0.0

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
3. Select media.
4. Inspect metadata.
5. Select QC profile.
6. Start analysis.
7. Observe progress.
8. Review result summary.
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
