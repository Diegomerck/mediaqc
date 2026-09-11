# Phase 3 — job orchestration

Phase 3 extends the existing managed engine, JSON-lines transport, SQLite projects
and React shell. No detector algorithms, evidence generation, reports or AI are
implemented. The authoritative specification package is unchanged.

## Run lifecycle

The engine implements `analysis.start`, `analysis.cancel`, `analysis.retry` and
`analysis.get`. Start accepts the exact documented project/media/profile/AI fields
and immediately returns a new UUID with `QUEUED`. Get, cancel and retry accept
`analysis_run_id`. The read-only `profile.list` and `profile.get` methods provide
the specified built-in `general_technical_qc` 1.0.0 document for selection. Profile
editing and user-copy workflows are not introduced.

One run may be active per engine. A conflicting start, project change or inspection
returns a recoverable error. A project lease also prevents another engine from
recovering or running against a live project. Each analysis worker has its own
SQLite connection, cancellation token, process registry and cache directory.

Runs move through `QUEUED`, `INSPECTING`, `ANALYZING`, then a terminal state. Later
evidence/report stages are not executed. Preparation verifies the saved source
fingerprint, records bundled tool versions, and probes the source again. Changed
or missing sources fail visibly. Profile snapshots are stored in full, independently
of later profile changes. Retry retains the historical row and creates a new UUID
using the previous snapshot and media selection.

The detector contract and scheduler support enable/disable policy, `supports`,
sequential execution, per-detector persistence, progress and failure isolation.
Test-only detectors exercise these behaviors. The production registry is empty:
after preparation, a production run ends with `RUN_START_FAILED` explaining that
QC detectors are not installed. It never claims that unperformed QC passed.
Finding-producing detectors remain an explicit later-phase integration boundary.

## Events and responsive UI

The wire envelopes remain unchanged. Analysis status, progress, detector status
and terminal completed/failed/cancelled events carry the run ID. Writes share a
lock so asynchronous events cannot corrupt response framing. The Rust actor
dispatches events both between responses and while idle, retaining strict response
correlation and validation. Only Tauri event listen/unlisten permissions are added.

React provides inspected-media/profile selection, AI OFF, start/cancel/retry,
actual engine progress, stage, elapsed time, available media position, detector
checklist and saved run history. A persisted-state refresh recovers events that
arrive before subscription. No animation fabricates analysis progress.

## Cancellation and recovery

Cancel signals the run, stops scheduling and kills/reaps registered FFmpeg/ffprobe
processes. Terminal persistence is serialized against cancel acceptance. Pending
and active detector records become CANCELLED before the terminal event is emitted.
The worker then closes its database connection. Cancellation of an already-terminal
run returns `RUN_ALREADY_TERMINAL`.

Engine shutdown refuses new jobs, cancels active work and joins the worker. The
existing native bounded shutdown and kill-on-close Windows Job Object remain the
fallback for an unresponsive worker or abrupt process death. Source files remain
read-only; temporary output belongs in the run cache.

A small per-user recovery journal records only project DB paths for active runs;
SQLite remains authoritative. The desktop supplies its recovery directory as an
engine launch argument. On engine startup, accessible unlocked projects in this
journal have all nonterminal runs and active detector executions marked FAILED
with `ENGINE_INTERRUPTED`. Project opening applies the same recovery rule before
exposing history, including projects not recorded by an older engine. Inaccessible
or currently owned projects are deferred. There is no mid-file resume. The database
schema is unchanged because Phase 2 created the canonical run/execution tables.

## Validation

Focused Python tests cover lifecycle, sequential/conflicting starts, progress,
cancel, retry/snapshot preservation, disabled/unsupported detectors, failure
isolation, invalid transitions/parameters, project ownership, every nonterminal
recovery state, changed-source handling, and real FFmpeg cancellation/shutdown.

Native tests cover event interleaving, malformed progress, and real active FFmpeg
cleanup on cancellation, graceful shutdown and engine crash followed by recovery.
Frontend tests cover valid selection, responsive cancel, progress, terminal events,
retry and recoverable errors. All previous Phase 1/2 tests remain in the quality gate.

`npm run phase3:smoke` uses the existing packaged production-controller harness with
an empty PATH and a Unicode/spaces/apostrophe/ampersand directory. It verifies
queued start, cancellation, terminal/progress events, retry, preserved profile
snapshot and history across engine restart, explicit unavailable-detector failure,
and unchanged source bytes/mtime. `npm run check` retains all prior gates and adds
this smoke test. The Windows executable and bundled runtime are built by the
existing `desktop:build` gate; installer/signing and clean-machine validation
remain Phase 9.
