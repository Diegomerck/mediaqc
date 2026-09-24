# 02 — Architecture Specification

**Version:** 1.1.0

## 1. Architectural goals

- Offline-first.
- Windows-first.
- Portable analysis core.
- No required local server.
- Strong separation of UI and analysis.
- Reproducible deterministic detectors.
- Bounded memory usage for large files.
- Clean subprocess lifecycle.

## 2. Process model

### Desktop process

Responsibilities:

- windows/navigation;
- file/folder pickers;
- preferences UI;
- engine process lifecycle;
- IPC transport;
- displaying data returned by engine.

### Engine process

Responsibilities:

- SQLite;
- ffprobe/FFmpeg orchestration;
- detector execution;
- evidence generation;
- report generation;
- job state;
- structured logs.

The desktop process SHALL launch one managed engine process per application instance for V1.

The engine MAY use internal worker threads/processes.

## 3. IPC transport

Transport: child-process stdin/stdout.

Format: UTF-8 JSON, exactly one JSON object per line.

Reasons:

- no TCP port;
- no firewall prompt;
- no browser server;
- offline semantics;
- simple ownership/lifecycle.

Full protocol: `06_IPC_SPEC.md`.

## 4. FFmpeg model

Bundled binaries live within application resources.

The engine resolves FFmpeg path using application-provided resource configuration or its own packaged resource path.

Never assume `ffmpeg` exists on PATH.

Subprocess execution SHALL:

- pass argument arrays, not shell-concatenated strings;
- disable shell execution;
- capture stderr;
- support cancellation;
- record binary version per run;
- avoid command injection from file paths.

## 5. Media processing strategy

### Metadata
Use ffprobe machine-readable JSON.

### Audio
Prefer direct decode to float PCM stream/chunks when custom DSP is required.

PCM detectors may reuse a run-local float64 decode, streamed in bounded blocks.
Temporary PCM storage is capped at 1 GiB across a project's run caches; oversized
streams or unavailable cache storage fall back to direct decoding. Publish a cache
only after successful decode; remove partial data on cancellation/error/early close.
Remove PCM caches on terminal cleanup and under the project lease during recovery.
This does not authorize a source-file copy or an unbounded decoded-media cache.
Detector windows, sample ordering, thresholds and execution boundaries stay intact.
Video timestamp extraction uses four decoder threads within the single active
file; this does not permit parallel files. Original decoded timestamps are retained.

For EBU loudness/true-peak measurement, FFmpeg filters MAY be used if parsing is stable and covered by tests.

### Video
Decode frames incrementally.

Detectors MAY operate at:

- native frame rate;
- profile-defined sample rate;
- multiple passes.

The engine MUST NOT materialize the whole decoded video in RAM.

## 6. Internal engine layers

```text
engine/
  app/
  ipc/
  jobs/
  media/
  detectors/
    audio/
    video/
  qc/
  evidence/
  reports/
  db/
  models/
  logging/
```

Suggested dependency direction:

```text
ipc -> application services
jobs -> detector orchestration
detectors -> media primitives + qc profile models
evidence -> media primitives
db -> persistence models/repositories
reports -> db read models + evidence
```

UI concepts must not leak into detectors.

## 7. Job execution model

A run owns:

- job cancellation token;
- process registry;
- progress state;
- detector execution state;
- evidence queue;
- DB transaction boundaries.

Required Phase 10 concurrency:

- exactly one active media file per engine, including inspection and evidence;
- no parallel file processing or inspection prefetch;
- retain current detector scheduling; configurable concurrency is future work.

Optimization SHOULD favor shared decode passes when practical, but correctness takes priority over premature performance work.

## 8. Crash recovery

On engine startup:

- find runs in non-terminal states;
- mark them `FAILED` with reason `ENGINE_INTERRUPTED` unless a safe resumable design is later specified;
- do not pretend they completed.

V1 does not require mid-file resume.

Phase 10 adds explicit pending-item continuation, not resumable analysis runs.
Section 15 defines reconciliation of batch items with the recovered run records.

## 9. File identity

Persist:

- absolute path;
- file size;
- modification time;
- fast fingerprint.

Recommended fast fingerprint:

- hash metadata + first N MiB + last N MiB;
- algorithm: SHA-256.

Full-file hash MAY be optional because professional media can be very large.

A run SHALL store the fingerprint used.

If file metadata/fingerprint changes between inspection and analysis, warn or re-inspect.

## 10. Engine capability handshake

At startup UI requests:

```json
{
  "method": "system.capabilities"
}
```

Engine reports:

- app/engine version;
- protocol version;
- FFmpeg version;
- ffprobe version;
- detector registry and versions;
- optional AI capability;
- GPU capability if detected;
- schema version.

## 11. Configuration layers

Precedence:

1. built-in safe defaults;
2. application settings;
3. project settings;
4. selected QC profile;
5. run-specific explicit overrides, only where the spec allows them.

No environment variable should be required for normal end-user operation.

## 12. Platform abstraction

Windows is required.

Cross-platform-safe code SHOULD be used for:

- paths;
- SQLite;
- subprocess argument handling;
- timestamps;
- detector math.

Windows-specific code should be isolated under platform/adapters so later macOS/Linux ports do not require detector rewrites.

## 13. Failure isolation

A detector failure SHALL yield:

- detector execution record = failed;
- structured error;
- log reference;
- continued run when remaining detectors can safely continue.

A fatal media decode/input failure MAY fail the run.

## 14. Architecture acceptance criteria

- No listening TCP/UDP port required for core V1.
- Killing the UI terminates the owned engine.
- Cancelling analysis terminates engine-owned FFmpeg children.
- Large fixture processing keeps memory bounded.
- UI can restart, reopen project, and read completed results.
- Engine stdout contains protocol JSON only.

## 15. Phase 10 batch coordinator

### Ownership and execution

The local Python engine owns a persistent sequential coordinator above the existing
single-run manager. SQLite is authoritative; React never schedules the next file.
No new service, transport, dependency, decoder, or detector algorithm is required.

Use a single scheduler reservation shared by batch execution, standalone analysis,
and inspection. Only one batch may be IMPORTING, RUNNING, PAUSING, or STOPPING per
engine. A paused batch retains its saved queue but no active worker; another batch
may run only through an explicit start. Resume must reacquire the reservation.
Project switching is rejected while discovery/processing/cleanup is active; paused
and terminal batches can be reopened later. Shutdown stops active work before DB
connections and the project lease are released.

Discovery runs asynchronously, performs bounded traversal with incremental DB
inserts, and never probes every file in the request dispatcher. Keep directory
enumeration, sorting, IPC pages, and exclusions bounded rather than holding the
entire tree in RAM. Inspection for the current item runs in a cancellable worker,
reusing fingerprint/probe logic and owned child-process cleanup.

Claim one PENDING item as INSPECTING in a short transaction. After successful
inspection, create exactly one analysis run and attach its ID to that item in the
same transaction, before launching it. Do not create analysis runs for the rest
of the queue. Existing `analysis_runs` and detector/finding/evidence records remain
authoritative; batch items record scheduling, not duplicated QC results.

Use separate SQLite connections per thread and short transactions. Serialize item
claiming, Pause/Stop acceptance, and terminal commits. Advance only after the current
worker and its owned processes have cleaned up, not simply on a terminal event.
Persist before publishing events. Public analysis start/retry/cancel must not bypass
batch ownership: controls on batch-owned active runs return BATCH_CONFLICT and
direct the caller to batch controls; internal cancellation still reuses JobManager.

### States and transitions

| Batch state | Permitted next states / cause |
|---|---|
| IMPORTING | READY after complete discovery; STOPPING on Stop; FAILED on fatal discovery error; INTERRUPTED on crash |
| READY | RUNNING on Start with candidates/settings; STOPPING on Stop |
| RUNNING | PAUSING on Pause with active file; PAUSED on Pause between files; STOPPING on Stop; COMPLETED when queue exhausted; FAILED on infrastructure failure; INTERRUPTED on crash |
| PAUSING | PAUSED after cleanup with pending files; COMPLETED if the last file finishes; STOPPING on Stop; FAILED or INTERRUPTED |
| PAUSED | RUNNING on Resume; STOPPING on Stop |
| STOPPING | STOPPED after cancellation and cleanup; reconciliation completes this intent after a crash |
| INTERRUPTED | RUNNING only on explicit Continue pending files for a fully discovered batch with a saved profile; STOPPING on Stop |
| COMPLETED / STOPPED / FAILED | Terminal; retry requires a new batch |

INTERRUPTED is quiescent and reportable, but conditionally resumable as above.
Repeated Pause during PAUSING/PAUSED, Resume during RUNNING, Start during RUNNING,
or Stop during STOPPING/STOPPED returns current state without duplicate work.
Other invalid transitions return BATCH_INVALID_STATE. Resume during PAUSING is
invalid; wait until the current file finishes. An exhausted batch becomes COMPLETED
even if some items are ERROR; show "Completed with errors" rather than a batch PASS.

| Item state | Permitted next states / meaning |
|---|---|
| PENDING | INSPECTING when claimed; CANCELLED on Stop |
| INSPECTING | RUNNING when a run is created/linked; ERROR on inspection failure; CANCELLED on Stop |
| RUNNING | COMPLETED, ERROR, or CANCELLED according to the linked run |
| COMPLETED / ERROR / CANCELLED | Terminal; never reset for retry |
| EXCLUDED | Import record only; never scheduled or included in queue totals |

Pause does not freeze a detector or subprocess. It allows the active file, including
evidence and enabled optional AI, to finish and schedules nothing further. Stop
first persists STOPPING and blocks new claims, then signals active cancellation and
terminates owned ffprobe/FFmpeg children. Pending items become CANCELLED without
creating synthetic runs. A linked active run must reach CANCELLED and emit its
existing terminal event. A completion committed before Stop remains COMPLETED.
If Stop wins the terminal-commit race, the active run/item is CANCELLED. Preserve
partial findings for diagnosis without giving incomplete runs a verdict.

Per-file media/detector failures produce ERROR and allow safe continuation. Missing
bundled tools, lost persistence, or other infrastructure failure halts scheduling,
cancels owned work, and records FAILED when storage is available; unattempted items
remain PENDING for explicit new-batch retry. Never continue while durable state is
unknown. Surface persistence failure to the UI even if it cannot be written to DB.

### Recovery and retries

Acquire the project lease before recovery. Reconcile on startup via the existing
journal and whenever a project opens; recovery must not depend on a journal entry
for each unstarted item. Completed runs always win over stale active item state.
Failed/cancelled runs map to ERROR/CANCELLED. Recover nonterminal runs as
FAILED / ENGINE_INTERRUPTED under the existing rule. An INSPECTING item with no
run becomes ERROR / ENGINE_INTERRUPTED. Do not fabricate or restart a run.

For a fully discovered RUNNING/PAUSING batch interrupted unexpectedly, preserve
PENDING items, reconcile active items, and enter INTERRUPTED when pending work
remains; if all items are terminal, finalize COMPLETED. Offer Continue pending files
with the original profile snapshot and AI mode, without retrying ERROR items.
A persisted STOPPING intent finishes as STOPPED and cancels remaining pending items.
Interrupted discovery has `discovery_completed_at = NULL`, retains its partial
import records, and cannot continue; require a new import. READY/PAUSED and terminal
batches otherwise retain state. Graceful closure stops active batches; it does not
turn a deliberately stopped queue into resumable pending work.

Retry selected ERROR/CANCELLED items (or unattempted items from a FAILED batch) as
a new batch with original-item references and the saved settings. The old batch,
runs, findings, and reports remain. Explicit retry performs a fresh source identity
capture; ordinary Resume never silently accepts a changed source.

### Read models, progress, and presentation

Aggregate/filter in SQLite; return compact batch metadata plus bounded item pages.
Do not call full project summaries or `analysis.get` for every row. Revisions are
monotonic per batch: increment on persisted import/state/item changes and on linked
run disposition changes that affect the displayed summary. Commit the latter with
the disposition update. Progress events carry a separate monotonic sequence within
an engine session; snapshots are the recovery source if events are lost.

For a frozen queue, total excludes EXCLUDED; processed = COMPLETED + ERROR;
processing = INSPECTING + RUNNING (0 or 1). The partition is:
total = PASS + WARN + FAIL + ERROR + CANCELLED + processing + PENDING.
Use authoritative completed-run verdicts; an inconsistent missing verdict is a
recovery error, never an assumed PASS. Needs attention = WARN + FAIL + ERROR.

Overall file-weighted progress = (processed + active_fraction) / total, or 0 for
an empty queue. `active_fraction` is engine-derived, clamped below 1 until terminal
commit, and monotonic within that item's attempt; unknown inspection progress is
indeterminate (contributes 0). Include evidence/finalization before completion.
Cancelled attempts contribute 0; Stop can lower the displayed estimate, which must
be explained by the stopped state. Do not present 100% QC coverage for unattempted
cancelled items. The estimate is not time-weighted or an ETA; never fake smoothing.

Engine presentation adapters derive optional human-readable comparisons from saved
measurements, finding thresholds, and the saved run profile only. They may perform
unit-aware display arithmetic but never change finding severity, raw data, or QC
policy. Unknown schemas fall back to saved descriptions and labeled values.

Batch report generation takes a consistent DB snapshot and saves a unique artifact
and revision. Permit only paused/terminal batches; reject Resume/Start while report
generation owns the scheduler reservation. Do not let a synchronous report request
block Stop of another running batch. Existing detailed report export must likewise
avoid monopolizing the dispatcher during active batch work (defer with BATCH_BUSY).
Keep report memory bounded through paged/streamed summary rows; no bulk evidence.
