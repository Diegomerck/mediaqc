# Phase 1 — Desktop shell and engine IPC

Implemented on `phase/01-desktop-engine-ipc`. The authoritative specifications,
`AGENTS.md`, and relevant Phase 0 files were read before changes. No architecture
conflict was found. Specifications and the original Phase 0 validation records
remain unchanged. No commit, push, or branch switch is part of this task.

## Architecture and lifecycle

React displays engine diagnostics and exposes Start, Ping, Stop and Restart
controls. Four explicitly permitted Tauri commands connect the main window to
the Rust controller. The frontend cannot supply process paths or arbitrary
commands. Static frontend assets are embedded; there is no HTTP backend or
development server.

One background Rust actor owns one engine session per application instance.
Repeated Start while ready returns the same session. The controller resolves
`resources/engine/mediaqc-engine.exe` relative to Tauri's resource directory,
independent of working directory and PATH. PyInstaller 6.19.0 produces the complete
one-folder Python 3.12 runtime; Python is a developer dependency only.

Startup spawns the child with argument arrays and piped stdin/stdout/stderr,
assigns a Windows kill-on-close Job Object, waits for `engine.ready`, requests
capabilities, and rejects incompatible protocol versions. Readiness and response
deadlines are five seconds each. Dedicated readers drain stdout and stderr;
request correlation uses new UUIDs. The actor checks idle process health every
50 ms. React refreshes the small status snapshot every 500 ms, including after
an unexpected idle exit. Blocking subprocess operations never run on the UI
thread.

Stop and application exit send `system.shutdown`, close input, allow up to two
seconds for the shutdown exchange and exit, then kill and reap if necessary.
Forced shutdown is distinguished from graceful shutdown in the UI. Failed
sessions are disposed before Restart becomes available. Closing the last
controller handle also shuts down its session. Windows Job Object ownership
terminates the engine on abrupt desktop death; stdin EOF is an additional
engine-side exit path. There are no workers, media-tool children, jobs or DBs in
this phase.

Startup/runtime errors include a code, message, recovery action and local log
path. Stderr is stored in `engine.log` under Tauri's per-user application log
directory, with one previous-session file. Each file is capped at 1 MiB while
stderr continues to drain. No protocol request contents or media contents are
logged. The stdout queue is bounded at 64 messages and each protocol line at
1 MiB. These are transport resource limits, not QC policy thresholds.

## Protocol behavior

Engine messages are UTF-8 JSON objects with exactly one LF terminator per object.
Stdout contains protocol messages only. Envelopes exactly follow
`specs/06_IPC_SPEC.md`:

```json
{"type":"request","protocol_version":"1.0","request_id":"uuid","method":"system.ping","params":{}}
{"type":"response","protocol_version":"1.0","request_id":"uuid","ok":true,"result":{"pong":true}}
{"type":"response","protocol_version":"1.0","request_id":"uuid","ok":false,"error":{"code":"INVALID_REQUEST","message":"Human-readable message","details":{}}}
{"type":"event","protocol_version":"1.0","event":"engine.ready","data":{}}
```

Implemented methods:

- `system.ping`: returns `{"pong":true}`.
- `system.capabilities`: engine version, protocol version, schema contract
  version, platform, tool/AI availability and detector registry.
- `system.shutdown`: acknowledges with an empty result and exits, ignoring
  subsequent buffered requests.

The IPC specification defines no `system.version` method. Versions are exposed
through capabilities and the desktop version is shown in diagnostics. Existing
development version `0.0.0` is retained. `schema_version: 1` describes the V1
contract; no schema is created or database opened. FFmpeg/ffprobe report
`available: false`, their versions are null, local AI is unavailable, and
`detectors` is empty. No GPU is detected or advertised.

System methods accept empty params only. Unknown/later-phase methods return
`METHOD_NOT_FOUND`. Invalid envelopes with a string request ID receive correlated
`INVALID_REQUEST`; incompatible versions receive
`PROTOCOL_VERSION_UNSUPPORTED`. Invalid JSON/UTF-8, duplicate keys, non-JSON
constants, oversized input or missing/non-string IDs cannot be safely correlated
using the specified envelope, so they produce diagnostics only and the reader
continues where possible. No null or invented request ID is introduced. Input
without a final newline is discarded at EOF. JSON escaping keeps even invalid
surrogate IDs from crashing output encoding.

## Files

| Area                                | Created or changed files                                                                                                                               |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Native controller                   | `apps/desktop/src-tauri/src/engine.rs`, `ownership.rs`, `protocol.rs`, `lib.rs`, `main.rs`                                                             |
| Native configuration                | `apps/desktop/src-tauri/Cargo.toml`, `Cargo.lock`, `build.rs`, `tauri.conf.json`                                                                       |
| Native tests                        | `apps/desktop/src-tauri/tests/lifecycle.rs`, `tests/fixtures/engine_stub.py`, `examples/engine_smoke.rs`                                               |
| Frontend                            | `apps/frontend/src/App.tsx`, `engine.ts`, `styles.css`, `tests/App.test.tsx`, `package.json`                                                           |
| Engine                              | `engine/entrypoint.py`, `engine/src/mediaqc_engine/__init__.py`, `__main__.py`, `app/__init__.py`, `app/system.py`, `ipc/__init__.py`, `ipc/server.py` |
| Engine tests                        | `engine/tests/test_ipc.py`; existing package/import tests retained                                                                                     |
| Tooling                             | `tools/build_engine.py`, `smoke_engine.py`, `smoke_lifecycle.py`, `check.mjs`, `tests/repository.test.mjs`                                             |
| Dependencies / generated-file rules | `.gitignore`, `package.json`, `package-lock.json`, `pyproject.toml`, `uv.lock`                                                                         |
| Documentation                       | `docs/DEVELOPMENT.md`, `docs/PHASE_1.md`, `docs/PHASE_1_VALIDATION.md`                                                                                 |

Generated command permission files are rebuilt from `build.rs` and ignored.
The only added runtime npm dependency is the Tauri API. Rust directly declares
already-locked serde, serde_json, UUID and Windows API crates. PyInstaller is
developer-only. No cloud SDK, network service or media-processing dependency was
introduced.

## Acceptance and scope

Automated frontend tests cover launch, handshake completion, ping result display,
clean/forced stop, startup errors, idle crashes, restart and missing bridge.
Native tests exercise real child processes, including malformed framing,
incompatible startup, timeout, stderr pressure, wrong correlation, crashes,
restart and forced termination. The packaged smoke performs 10,000 sequential
pings with an empty PATH and an executable/working path containing spaces,
Unicode, apostrophe and ampersand. The native smoke uses the production controller
and verifies engine termination after abrupt parent death.

Validation commands, outcomes and limitations are recorded in
[PHASE_1_VALIDATION.md](PHASE_1_VALIDATION.md).

No Phase 2+ functionality is implemented: no projects, SQLite functionality,
media selection/inspection, FFmpeg/ffprobe integration, jobs, detectors, evidence,
reports or AI. Cancellation/analysis events and clean-machine installer tests
remain in their specified later phases.
