# Phase 2 — projects and media inspection

The React shell uses native Windows dialogs to create/open local projects and
select source media. It displays persisted file/container/stream metadata,
inspection failures and missing/changed-source warnings. Recent project paths and
last-opened timestamps are a UI shortcut cache; SQLite remains authoritative.

The existing managed Python engine handles `project.create`, `project.open`,
`project.get` (empty params for the active project) and `media.inspect`. The exact
JSON-lines request, response and event envelopes remain unchanged. Application
errors retain the open engine session, while protocol/process failures retain the
existing restart workflow. System ping, capabilities and shutdown remain available.

Each new empty project directory receives `project.sqlite`, the canonical numbered
schema-1 migration and the specified output/cache/log directories. Initial creation
is transactional. Existing projects are validated read-only before opening in WAL
mode with foreign keys and NORMAL synchronization. Unsupported versions are rejected
without migration or modification. Inspections insert asset/stream records atomically;
reinspection preserves earlier records. Reserved later-phase schema tables have no
jobs, detectors, reporting or AI implementation.

Source files are opened read-only. The bounded SHA-256 fingerprint combines size,
nanosecond modification time and the first/last 4 MiB. Identity is checked again
after probing. Original media is neither copied nor modified, and no sidecars are
created beside it. ffprobe receives an argument array, with only local-file protocol
access. JSON stdout and stderr are captured separately in the engine cache. A
30-second deadline and 64-KiB metadata/output bounds prevent an unbounded probe;
larger metadata returns a visible structured failure. Probe failures retain a
bounded stderr excerpt with the failed asset record.

The input reader can receive shutdown during inspection. It interrupts the owned
probe, allowing database cleanup and shutdown acknowledgement. The native controller
retains a bounded shutdown fallback and its Windows kill-on-close Job Object, so
engine and media-tool descendants cannot outlive the desktop parent.

## Bundled media tools

Run `npm run media:prepare` once during developer bootstrap. The pinned URL and
SHA-256 are in `config/media-tools.json`. The script verifies the archive before
extracting FFmpeg/ffprobe 8.1.2, LICENSE and README into ignored `engine/vendor/ffmpeg`.
It records version/configuration output and provenance. `engine:build` copies this
directory beside the standalone engine. Runtime resolution uses that directory only;
it never falls back to an end user's PATH or downloads tools.

The selected [Gyan essentials build](https://www.gyan.dev/ffmpeg/builds/) is GPLv3.
License, upstream README, source URL, checksum and full build configuration travel
with the runtime. This is an unsigned development package; the public installer,
signing and final distribution/source-compliance review remain Phase 9 work.

## Validation

Synthetic fixtures cover PCM WAV and FFV1 video, corrupt/non-media files, absent
files/tools, process timeouts, malformed metadata, Unicode/spaces/shell punctuation,
source immutability, migration rollback and project reopening across engine instances.
Frontend tests cover create/open/inspect, failures and cancelled dialogs. Native
tests preserve Phase 1 lifecycle behavior and cover recoverable application errors
and shutdown during an active inspection.

`npm run check` retains all existing gates and adds `phase2:smoke`. The new smoke
uses the production Rust controller and packaged engine/tools with an empty PATH
from a directory containing Unicode, spaces, an apostrophe and `&`. It inspects a
generated WAV, restarts the engine, reopens persisted metadata, checks missing-media
error recovery and ping, and verifies source bytes/mtime are unchanged.

The Windows build remains `tauri build --no-bundle -- --locked`: an executable plus
its complete `resources/engine` folder, without an installer. The automated native
smoke exercises the production controller; frontend workflow validation uses DOM tests.
