# Phase 1 validation record

Final validation resumed on 2026-09-10 on `phase/01-desktop-engine-ipc`.
No implementation was restarted. Only pending formatting was applied before
one complete final quality-gate run. No test, lint or type rule was disabled.

Final result: **PASS — all 18 gates, exit code 0**. The Windows release rebuilt
successfully and the native smoke confirmed graceful shutdown and abrupt-parent
cleanup (observed engine PID 11072 terminated).

## Quality-gate commands and results

`npm run check` executes every row below, preserving all 15 Phase 0 gates and
adding three engine/native packaging gates. Its final log is
`.cache/phase1-check-final.log`.

| Command                       | First run     | Second run   | Final run                            |
| ----------------------------- | ------------- | ------------ | ------------------------------------ |
| `npm run format:check`        | PASS          | PASS         | PASS                                 |
| `npm run lint`                | FAIL          | PASS         | PASS                                 |
| `npm run typecheck`           | PASS          | PASS         | PASS                                 |
| `npm run python:format:check` | PASS          | PASS         | PASS                                 |
| `npm run python:lint`         | FAIL          | PASS         | PASS                                 |
| `npm run python:typecheck`    | FAIL          | PASS         | PASS                                 |
| `npm run python:test`         | PASS          | PASS         | PASS: 25 tests                       |
| `npm run rust:format:check`   | PASS          | PASS         | PASS                                 |
| `npm run test:baseline`       | PASS          | PASS         | PASS: 3 tests                        |
| `npm run test:frontend`       | PASS          | PASS         | PASS: 6 tests                        |
| `npm run build`               | PASS          | PASS         | PASS                                 |
| `npm run engine:build`        | PASS          | PASS         | PASS                                 |
| `npm run engine:smoke`        | PASS          | PASS         | PASS                                 |
| `npm run rust:check`          | PASS          | PASS         | PASS                                 |
| `npm run rust:lint`           | PASS          | FAIL         | PASS                                 |
| `npm run rust:test`           | PASS          | PASS         | PASS: 3 protocol + 7 lifecycle tests |
| `npm run desktop:build`       | FAIL          | PASS         | PASS                                 |
| `npm run native:smoke`        | Not yet added | PASS         | PASS                                 |
| `npm run check`               | FAIL, exit 1  | FAIL, exit 1 | PASS, exit 0                         |

The first two logs are `.cache/phase1-check-1.log` and
`.cache/phase1-check-2.log`. Earlier failures were corrected as follows:

- First run: frontend test assertions/rejection typing, one Python line length,
  and a test helper's Python type annotation. A first attempt to remove an
  unnecessary TypeScript assertion exposed a compiler error in the desktop
  build hook; tests now query the actual disabled attribute without assertions.
- Second run: Clippy required the Rust test module to follow production items.
  It was moved, without suppressing Clippy.
- Final review: invalid escaped-surrogate request IDs could fail output encoding.
  JSON escaping was corrected and a regression test added. The package smoke was
  extended to execute from a path containing spaces, Unicode, apostrophe and `&`.

## Command expansions

Python gates run `uv run --locked ruff format --check .`,
`uv run --locked ruff check .`, `uv run --locked mypy`, and
`uv run --locked pytest`.

Rust gates run:

```powershell
cargo fmt --all --manifest-path apps/desktop/src-tauri/Cargo.toml -- --check
cargo check --locked --all-targets --manifest-path apps/desktop/src-tauri/Cargo.toml
cargo clippy --locked --all-targets --manifest-path apps/desktop/src-tauri/Cargo.toml -- -D warnings
cargo test --locked --manifest-path apps/desktop/src-tauri/Cargo.toml
```

Frontend gates run Prettier, ESLint with `--max-warnings 0`, both TypeScript
projects, `node --test tests/repository.test.mjs`, `vitest run`, and `vite build`.
The desktop build is `tauri build --no-bundle -- --locked` from `apps/desktop`.
Its build hook runs `npm run desktop:prepare --prefix ../..`, which packages
the engine and builds the frontend.

Packaging/smoke commands are:

```powershell
uv run --locked python tools/build_engine.py
uv run --locked python tools/smoke_engine.py
cargo build --locked --example engine_smoke --manifest-path apps/desktop/src-tauri/Cargo.toml
uv run --locked python tools/smoke_lifecycle.py
```

The build script invokes the pinned PyInstaller with `--onedir --console`,
repository-local dist/work/spec directories and the engine source path.

## Additional commands

- `npm run format`, `uv run --locked ruff format .`, and
  `cargo fmt --all --manifest-path apps/desktop/src-tauri/Cargo.toml`: PASS during
  implementation. The resumed final pass formatted only `docs/PHASE_1.md`, the
  changed Python server/test/smoke files and Rust sources.
- `cargo generate-lockfile --offline --manifest-path apps/desktop/src-tauri/Cargo.toml`:
  PASS; only four existing locked crates were added as direct dependencies.
- `uv lock`, `uv sync --locked`, and
  `npm install --workspace @mediaqc/frontend @tauri-apps/api@2.11.0 --save-exact`:
  PASS. Initial sandbox tool/registry access failed and was retried with approval.
  The npm install reported zero known vulnerabilities.
- `git diff --check`: PASS.
- `git diff --exit-code -- MASTER_SPEC.md AGENTS.md README.md SPEC_MANIFEST.json specs docs/PHASE_0.md docs/PHASE_0_COMMANDS.md`:
  PASS. The authoritative package and Phase 0 records have no content changes.
- Source inventory and method-dispatch review: PASS. Only Phase 1 system methods
  are implemented; later-phase capability entries report unavailable.

After recording these results, documentation formatting, whitespace/specification
checks, packaged-artifact hashes and exact Git status are verified separately;
no application source is changed after the final quality gate.

The repository-local developer environment is unchanged from Phase 0:

```powershell
$env:UV_CACHE_DIR = Join-Path $PWD '.cache/uv'
$env:CARGO_HOME = Join-Path $PWD '.tools/cargo'
$env:RUSTUP_HOME = Join-Path $PWD '.tools/rustup'
$env:PATH = (Join-Path $PWD '.tools/bootstrap/bin') + ';' + (Join-Path $PWD '.tools/cargo/bin') + ';' + $env:PATH
```

## Smoke evidence and limits

The final standalone smoke emitted the specified ready event, capabilities,
10,000 correlated ping responses, a shutdown response, and exited with code 0.
The logged example ping response was:

```json
{
  "type": "response",
  "protocol_version": "1.0",
  "request_id": "355772f8-4a55-44b5-8740-d293b6a6b52e",
  "ok": true,
  "result": { "pong": true }
}
```

The production native controller smoke verifies readiness, capabilities, ping,
graceful shutdown and Windows Job Object cleanup after abrupt parent termination.
The release artifacts are `apps/desktop/src-tauri/target/release/mediaqc-desktop.exe`
and its complete `resources/engine/` directory.

Validation ran on Windows 11 x64 with Python 3.12.14. Interactive GUI clicking and
clean-machine installer validation were not performed. Frontend behavior was
tested through DOM tests, and real process IPC through native integration and
packaged-runtime smoke tests. Installer/signing and Windows matrix testing remain
in Phase 9.

PyInstaller lists optional non-Windows/standard-library modules in its analysis
warning file; the standalone Windows smoke passes without developer PATH entries.
Git may emit checkout LF/CRLF warnings. No compiler, lint, type or test failures
were suppressed. There is no Phase 2+ functionality, commit, push or branch change.
