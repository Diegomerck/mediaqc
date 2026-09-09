# 02 — Architecture Specification

**Version:** 1.0.0

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

Recommended V1 concurrency:

- one active analysis run by default;
- configurable detector/media worker concurrency later;
- avoid parallel full-file decodes unless benchmarks justify it.

Optimization SHOULD favor shared decode passes when practical, but correctness takes priority over premature performance work.

## 8. Crash recovery

On engine startup:

- find runs in non-terminal states;
- mark them `FAILED` with reason `ENGINE_INTERRUPTED` unless a safe resumable design is later specified;
- do not pretend they completed.

V1 does not require mid-file resume.

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
