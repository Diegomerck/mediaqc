# Phase 10 installed batch event regression

The native desktop controller rejected every Phase 10 `batch.*` event as
`ENGINE_PROTOCOL_ERROR: Invalid analysis event`. Selecting a file creates a batch
and emits discovery/status events before an analysis run exists. The controller
still allowed only the earlier `analysis.*` events and required an analysis run ID.
Startup and ping therefore worked, but importing media terminated the session.
This was a desktop protocol validation defect, not an MP4 decoder failure.

The fix accepts the eight documented batch event names, validates batch/session
UUIDs and integer revision/sequence fields, validates item/run correlation for
item changes (including a null run ID), and bounds batch progress. It forwards
the original envelope unchanged. Existing analysis validation remains intact;
unknown or malformed batch events still fail with `Invalid batch event`.
No engine, database, detector, profile, frontend, or dependency changes are needed.

## Focused regression evidence

- Before the fix, `documented_batch_events_reach_desktop_unchanged` failed with
  the exact reported code/message. The new native `--batch` smoke also lost the
  engine session immediately after MP4 import.
- After the fix, `cargo test --locked --manifest-path
apps/desktop/src-tauri/Cargo.toml --lib protocol::tests`: 6 passed, including
  all documented batch names, malformed/missing correlation fields, invalid
  ordering/progress, and existing analysis/response validation.
- `cargo test --locked --manifest-path apps/desktop/src-tauri/Cargo.toml
--test lifecycle event`: 2 passed (event interleaving and malformed analysis
  event rejection); 10 unrelated tests filtered out.
- `cargo run --locked --manifest-path apps/desktop/src-tauri/Cargo.toml
--example engine_smoke -- --batch <new-project-directory> <MP4>` passed with
  the existing bundled engine and `video.clean.001.mp4`. This uses the production
  native controller, unlike the earlier direct-Python batch smoke. It checks
  import, completed one-item QC, forwarded discovery/status/item/progress/terminal
  events, selected-run retrieval, and a healthy ping/session afterward.
  Source SHA-256 and last-write timestamp remained unchanged.
- `cargo fmt` and focused `cargo clippy --locked --manifest-path
apps/desktop/src-tauri/Cargo.toml --lib --example engine_smoke -- -D warnings`
  passed. No full gate, full suites, large batch, or benchmark rerun.

Logs are under `.cache/phase10-event-*.log`. The installed engine log was empty;
reproduction and diagnosis came from the native controller and protocol regression.

## Replacement installer

`npm run desktop:build:prepared` passed, reusing the existing engine and frontend
resources. `npm run release:installer` passed after retrying outside the sandbox
to access the cached NSIS/WebView2 resources. The first attempt failed with socket
access error 10013 after patching the executable's bundle marker. The retry warned
that the marker was no longer found; NSIS nevertheless completed successfully.
No dependencies were installed or downloaded, and no portable ZIP was rebuilt.

- Path: `C:\Dev\MediaQC\mediaqc\apps\desktop\src-tauri\target\release\bundle\nsis\MediaQC_0.0.0_x64-setup.exe`
- Size: 342,279,659 bytes.
- Generated: 2026-09-23 03:55:21 UTC (September 22 local time).
- SHA-256: `036cbbae8edc2cabfdf4c4e5947b2af4068b4d0eb8fb35b84c74ce246fc68336`.
- Build/package logs: `.cache/phase10-event-desktop-build.log` and
  `.cache/phase10-event-installer-retry.log`.

Installer execution and the original user MP4 remain for manual acceptance.

## Manual acceptance

Close MediaQC fully and install the replacement installer over the existing
installation. Launch from the installed shortcut, open the existing project,
and leave historical results intact. Select the same MP4 that reproduced the
failure. Confirm import reaches READY without a protocol error, select AI OFF,
and run QC. Confirm progress updates, a completed row, a usable selected-file
result, and a still-ready engine. Repeat selection and QC once to confirm a new
batch preserves the previous completed result. Reopen the project and confirm
both results remain. A completed QC verdict may be PASS, WARN, or FAIL according
to the actual source; the regression concerns engine/session failure.

The application version remains 0.0.0; use the newly generated artifact rather
than a previously copied installer. At the time of this focused fix, portable
ZIPs predated it. The 2026-09-24 installer and portable release now include the
fix; see [current validation](PHASE_10_VALIDATION.md) for artifact identities and
the successful four-file installed-app benchmark.
