# MediaQC development setup

The active implementation is Phase 0 of `MASTER_SPEC.md`: repository and quality
gates. Read `MASTER_SPEC.md`, `AGENTS.md`, `README.md`, and all Markdown files in
`specs/` before changing application code. Their precedence is authoritative.
The original specification package is retained unchanged.

## Windows prerequisites

These tools are developer requirements only. The eventual installer must bundle
the application runtimes as specified in `specs/10_WINDOWS_BUILD.md`.

- Windows 10/11 x64 and PowerShell.
- Node.js 24.12.0 and npm 11.6.2 (recorded in `.node-version` and `package.json`).
- Python 3.12.14, recorded in `.python-version`.
- uv 0.12.12. With Python installed: `python -m pip install uv==0.12.12`.
- Rustup. `rust-toolchain.toml` selects Rust 1.94.0, the Windows MSVC target,
  rustfmt and Clippy. Do not substitute the GNU target for the native build.
- Visual Studio 2022 Build Tools: **Desktop development with C++**, including
  MSVC v143 x64/x86 build tools and the Windows 10/11 SDK.
- Microsoft Edge WebView2 Runtime for launching the development window.

Official installation guidance: [Tauri Windows prerequisites](https://v2.tauri.app/start/prerequisites/),
[Rustup](https://rustup.rs/), [Node.js](https://nodejs.org/en/download), and
[uv installation](https://docs.astral.sh/uv/getting-started/installation/).
If native tools are absent, stop native validation and report it as blocked.
Installing the system C++ workload can require administrator access; the
repository bootstrap does not install it or change machine settings.

## Bootstrap

Run from the repository root after installing the prerequisites:

```powershell
npm ci
uv sync --locked
rustup show
cargo fetch --locked --manifest-path apps/desktop/src-tauri/Cargo.toml
```

`uv sync` creates `.venv` and installs the engine as an editable package. No
activation is necessary: `uv run --locked` selects the project environment.
Package registries are needed for an initial developer bootstrap; they are not
application runtime services. Subsequent checks can run from populated caches.
Neither the application nor these scripts start a local HTTP server.

## Quality gates

```powershell
npm run check
```

This runs every gate, prints individual PASS/FAIL results and exits nonzero when
any gate fails. It does not silently skip missing tools. Build the frontend before
running individual native checks because Tauri embeds its `dist` directory.

| Gate                                     | Exact standalone command                |
| ---------------------------------------- | --------------------------------------- |
| JS/TS/CSS/JSON/document formatting       | `npm run format:check`                  |
| JS/TS lint, zero warnings                | `npm run lint`                          |
| TypeScript, including tests/build config | `npm run typecheck`                     |
| Python formatting                        | `uv run --locked ruff format --check .` |
| Python lint                              | `uv run --locked ruff check .`          |
| Strict Python types                      | `uv run --locked mypy`                  |
| Python package tests                     | `uv run --locked pytest`                |
| Rust formatting                          | `npm run rust:format:check`             |
| Repository baseline tests                | `npm run test:baseline`                 |
| Frontend DOM tests                       | `npm run test:frontend`                 |
| All JavaScript tests                     | `npm test`                              |
| Static frontend build                    | `npm run build`                         |
| Rust compiler                            | `npm run rust:check`                    |
| Rust Clippy, zero warnings               | `npm run rust:lint`                     |
| Rust test target                         | `npm run rust:test`                     |
| Tauri executable, without installer      | `npm run desktop:build`                 |

The Rust aliases expand to:

```powershell
cargo fmt --all --manifest-path apps/desktop/src-tauri/Cargo.toml -- --check
cargo check --locked --all-targets --manifest-path apps/desktop/src-tauri/Cargo.toml
cargo clippy --locked --all-targets --manifest-path apps/desktop/src-tauri/Cargo.toml -- -D warnings
cargo test --locked --manifest-path apps/desktop/src-tauri/Cargo.toml
```

The desktop build runs `tauri build --no-bundle -- --locked` from `apps/desktop`.
Its configured build hook builds the frontend first. Installer creation, signing,
sidecars and engine packaging belong to later phases.

Apply formatting intentionally:

```powershell
npm run format
uv run --locked ruff format .
cargo fmt --all --manifest-path apps/desktop/src-tauri/Cargo.toml
```

Prettier excludes the authoritative specification package and generated files;
Ruff owns Python formatting and rustfmt owns Rust. Type checks are strict without
`skipLibCheck`, ignored imports or test-warning suppression.

## Empty desktop window

```powershell
npm run desktop:start
```

This builds the static frontend and runs Cargo with the `custom-protocol` feature
enabled by default. Tauri embeds the assets and opens an empty window containing
the MediaQC heading. There is no `devUrl`, HTTP server, hot-reload server, engine
process, application command handler or Tauri plugin. After editing the frontend,
close the window and rerun the command.

## Repository map

```text
apps/
  desktop/src-tauri/       Minimal native executable and Tauri configuration
  frontend/src/           Static React/TypeScript shell and utility CSS
  frontend/tests/         Vitest/Testing Library DOM smoke test
engine/
  src/mediaqc_engine/     Importable, typed Python namespace only
  tests/                  Installed-package and silent-import smoke tests
tests/
  repository.test.mjs     Specification, lockfile and shell boundary checks
  fixtures/manifests/     Reserved; no fixture generation in Phase 0
  fixtures/generated/    Ignored generated media directory
  golden/                 Reserved for later regression corpus
tools/
  check.mjs               CI-capable quality-gate runner
  generate_test_media/    Reserved; no FFmpeg integration yet
config/                   Shared formatter configuration
docs/                     Developer setup and Phase 0 implementation notes
specs/                    Unchanged authoritative specifications
```

Engine layers from `specs/02_ARCHITECTURE.md` will be added beneath the package in
their active phases. Empty placeholders are not implementations of those layers.

`config/app-icon.svg` is the source for the minimal native build icon. Its checked-in
ICO and PNG are required by Tauri's Windows resource build even without an installer.
Regenerate them from the repository root with:

```powershell
& node_modules/.bin/tauri.cmd icon config/app-icon.svg --output .cache/app-icons
Copy-Item .cache/app-icons/icon.ico apps/desktop/src-tauri/icons/icon.ico
Copy-Item .cache/app-icons/icon.png apps/desktop/src-tauri/icons/icon.png
```

## Dependency updates

Normal setup uses lockfiles without updating them. Intentional dependency updates
must modify exact manifest versions, regenerate the appropriate lockfile, inspect
the diff and run the full quality gate:

```powershell
npm install --package-lock-only --ignore-scripts
npm ci
uv lock
uv sync --locked
cargo generate-lockfile --manifest-path apps/desktop/src-tauri/Cargo.toml
npm run check
```

Commit `package-lock.json`, `uv.lock` and `apps/desktop/src-tauri/Cargo.lock` when
changes are approved for source control. Never commit dependencies, caches,
local toolchains, generated binaries or source media. No commit is part of setup.

## Phase discipline

Baseline tests demonstrate that the development harness works, not that media QC
works. The native crate has no application logic to unit-test yet; `cargo test`
still checks compilation of its test target. Add meaningful Rust tests when native
behavior is introduced. Detector regression fixtures, timestamp tolerances,
clean-file controls, IPC tests, database tests and packaging validation remain
mandatory in their corresponding later phases.

No Phase 1+ functionality is implemented here. No cloud service, account,
telemetry, media upload, Redis, PostgreSQL, Celery, Docker runtime, local backend,
SQLite behavior, media dependency or optional AI package is introduced.
