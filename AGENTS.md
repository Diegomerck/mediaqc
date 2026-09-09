# AGENTS.md — Mandatory AI Coding Agent Rules

These rules apply to Codex, Claude Code, Cursor agents, Copilot agents, and any autonomous/semi-autonomous code-generation workflow.

## 1. Specification authority

Before changing code, read:

- `MASTER_SPEC.md`
- this file
- every relevant file under `specs/`

Do not silently contradict the specification.

If code and spec disagree, change code unless the user explicitly directs a specification change.

---

## 2. Architectural prohibitions

You MUST NOT introduce for V1:

- cloud APIs as a required dependency;
- a local HTTP/web backend when stdio IPC satisfies the requirement;
- Redis;
- PostgreSQL;
- Celery;
- Kafka;
- RabbitMQ;
- Kubernetes;
- Docker as an end-user runtime requirement;
- required user accounts;
- mandatory telemetry;
- automatic media upload.

You MUST NOT change Tauri + React/TypeScript + local Python engine + SQLite without explicit specification amendment.

---

## 3. Source media safety

Treat source media as immutable.

You MUST NOT:

- overwrite it;
- rename it;
- move it;
- normalize it;
- repair it;
- modify metadata;
- create sidecar files next to it without explicit user action.

Temporary and evidence outputs belong in the project/cache directories.

Open source media read-only wherever platform/library semantics allow.

---

## 4. Detector rules

All detectors MUST:

- use canonical detector IDs;
- expose a version;
- implement the detector contract;
- read policy thresholds from the QC profile;
- return structured findings;
- never manipulate UI state directly;
- be independently testable;
- have regression fixtures;
- log failures with detector context.

Do not replace deterministic measurements with LLM reasoning.

---

## 5. Threshold rule

QC policy thresholds MUST live in QC profiles.

Forbidden:

```python
if true_peak > -1.0:
    fail()
```

Required pattern:

```python
limit = profile.audio.true_peak.max_dbtp
if measured_true_peak > limit:
    ...
```

Algorithmic constants MAY remain implementation details when they are not user/business policy.

---

## 6. IPC rules

UI and engine communicate only through the documented line-delimited JSON protocol.

- stdout from engine is reserved for protocol messages.
- diagnostic logging goes to stderr and log files.
- every request has a request ID.
- every response/event follows the documented envelope.
- malformed input returns a structured error when possible.
- protocol version is reported at startup/capabilities.

Do not print debugging prose to engine stdout.

---

## 7. Database rules

- SQLite is authoritative local persistence for V1.
- Use migrations/schema versioning.
- JSON payload columns are permitted only for flexible measurements/evidence metadata; do not hide core relational fields in blobs.
- Use UTC ISO-8601 timestamps in persisted metadata.
- Use seconds as floating-point media timeline units unless a field explicitly documents another unit.
- Do not delete completed analysis history merely because a new analysis is run.

---

## 8. Error handling

Bad media is expected input, not an exceptional product failure.

- Catch FFmpeg/ffprobe failures.
- Preserve stderr excerpts/log references.
- Convert media problems into structured engine errors and/or QC findings where appropriate.
- Never crash the desktop app because one detector failed.
- Mark the detector/run appropriately and continue when safe.

---

## 9. Cancellation and process hygiene

Cancellation MUST:

- stop scheduling new detector work;
- signal active workers;
- terminate owned FFmpeg/ffprobe child processes;
- persist `CANCELLED`;
- emit terminal job event;
- leave project DB consistent.

No orphan subprocesses.

---

## 10. Testing rules

Every new detector requires:

- unit tests;
- synthetic fixture tests;
- expected timestamp tolerance;
- clean-file false-positive checks.

Every bug fix requires a regression test unless technically impossible and documented.

Never change expected fixture output merely to make a failing implementation pass without proving the fixture expectation is wrong.

---

## 11. UI rules

UI MUST NOT implement signal-processing/media-analysis logic.

UI may:

- validate user input;
- display engine state;
- render findings/evidence;
- edit QC profile values;
- send commands.

Analysis belongs in the engine.

---

## 12. AI rules

Local AI is optional enhancement only.

AI MUST NOT:

- determine true peak, LUFS, frame rate, timestamps, clipping counts, or other deterministic measurements;
- modify raw detector measurements;
- hide an underlying finding;
- require internet;
- prevent the run from completing if AI fails.

AI output must be stored separately from deterministic detector output.

---

## 13. Security/privacy rules

- Do not add analytics SDKs by default.
- Do not add crash upload services by default.
- Do not make outbound network calls in core workflows.
- Avoid storing unnecessary user information.
- Never include source media content in logs.
- Hash/fingerprint files locally only.

---

## 14. Code quality rules

Prefer:

- typed interfaces;
- small pure functions for DSP/CV calculations;
- dependency injection around subprocess/DB/filesystem boundaries;
- deterministic tests;
- explicit cancellation tokens;
- structured logging.

Avoid:

- giant detector classes;
- global mutable state;
- magic thresholds;
- hidden singleton process managers;
- parsing human-readable CLI output when machine-readable FFmpeg output is available.

---

## 15. Phase discipline

Implement only the active phase from `MASTER_SPEC.md`.

Do not opportunistically add:

- watch folders;
- cloud AI;
- auto-repair;
- subtitle QC;
- lip-sync;
- batch farms;
- network collaboration;
- licensing servers.

Create clean extension points instead.

---

## 16. Definition of done for an agent task

A task is not complete until:

1. code is implemented;
2. formatting/linting passes;
3. relevant tests pass;
4. acceptance criteria are checked;
5. docs/spec are updated if behavior changed;
6. no new unapproved architecture dependency was introduced;
7. results are summarized with files changed and commands run.
