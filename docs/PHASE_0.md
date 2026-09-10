# Phase 0 implementation and validation

Date: 2026-09-09. Branch: `phase/00-foundation`.

## Authority and scope

`MASTER_SPEC.md`, `AGENTS.md`, `README.md`, and all ten Markdown specifications
were read completely before implementation. The implementation acknowledges and
follows `AGENTS.md`, including source immutability, architecture, quality gates
and phase discipline. The existing specification package is unchanged.

Only Phase 0 is implemented. The native entry point is configured to open a static React page.
The Python package has no entry point or engine behavior. There is no engine
launch, protocol implementation, media inspection, FFmpeg, SQLite functionality,
detector, AI, report, installer, application account, telemetry or upload.

Phase 0 exit criteria now pass: the empty native shell builds, all quality-gate
commands run successfully, and no QC logic is implemented. Phase 1 remains
out of scope and has not been started.

## Implementation choices

- npm workspaces separate the frontend and desktop build dependencies.
- Initial package versions are `0.0.0`; this is a development foundation.
- Tauri 2 embeds Vite's static assets with its custom protocol. There is no
  local HTTP server or development server command.
- A few local utility CSS classes satisfy the initial styling foundation.
- Python uses a typed `src` package, an empty runtime dependency list and uv.
- Tests cover the installed Python package, silent import, accessible empty
  frontend, specification package presence, lockfiles and desktop boundaries.
- Reserved fixture/golden/generator directories contain placeholders only.
- Native icons are generated from the repository SVG with Tauri's own CLI.
- CI-capable commands live in `package.json` and `tools/check.mjs`; no hosted
  service is required to execute them.
- Production installer identity and distribution assets can be finalized in
  the packaging phase; `com.mediaqc.desktop` identifies this development shell.

## Direct dependencies

All direct manifest versions are exact. Transitive JS, Python and Rust versions
are captured in `package-lock.json`, `uv.lock` and `Cargo.lock`, respectively.

| Dependency                | Version | Purpose                                            |
| ------------------------- | ------- | -------------------------------------------------- |
| React / React DOM         | 19.3.0  | Static frontend runtime                            |
| TypeScript                | 5.9.3   | Strict frontend, test and build-config checking    |
| Vite                      | 7.3.6   | Static frontend bundling                           |
| Vite React plugin         | 5.2.0   | React JSX transform                                |
| Vitest                    | 4.1.11  | Frontend unit/DOM test runner                      |
| Testing Library React     | 16.3.3  | Accessible DOM queries and React rendering         |
| jsdom                     | 28.0.0  | Test-only DOM on the available Node 24.12 runtime  |
| React / React DOM types   | 19.3.0  | React TypeScript declarations                      |
| Node types                | 22.20.2 | Node API declarations for build configuration      |
| ESLint                    | 10.10.0 | JavaScript/TypeScript linting                      |
| ESLint JS rules           | 10.0.1  | Recommended baseline lint rules                    |
| typescript-eslint         | 8.70.0  | Strict, type-aware TypeScript linting              |
| React hooks lint plugin   | 7.1.1   | React hook correctness                             |
| React refresh lint plugin | 0.5.6   | Component export consistency                       |
| globals                   | 17.12.0 | Browser/Node lint environments                     |
| Prettier                  | 3.9.6   | JS/TS/CSS/JSON/document formatting                 |
| Tauri CLI                 | 2.11.4  | Native build configuration and executable build    |
| Tauri crate               | 2.11.5  | Minimal native desktop window                      |
| tauri-build               | 2.6.3   | Native resource and configuration build step       |
| Hatchling                 | 1.27.0  | Python package build backend                       |
| Ruff                      | 0.15.0  | Python formatting and linting                      |
| mypy                      | 1.19.1  | Strict Python type checking                        |
| pytest                    | 9.0.2   | Python package tests                               |
| uv                        | 0.12.12 | Developer-only dependency locking and environments |

Rust 1.94.0 (including rustfmt/Clippy), Node 24.12.0/npm 11.6.2 and Python
3.12.14 are the selected developer toolchains. Rust and uv were installed in
ignored `.tools` directories without changing system PATH. The existing bundled
Python 3.12.14 interpreter was used to create `.venv`; no system Python was
installed. The user subsequently installed Visual Studio Build Tools 2022 and the Windows
SDK. Native validation detected MSVC 14.44.35207 and SDK 10.0.26100.0. The agent
did not install or modify those system components.

## Validation

After the C++ toolchain installation and Tauri dependency alignment, the four
previously failing native commands passed individually. The subsequent complete
`npm run check` executed all 15 gates and returned **exit code 0**.

| Check                     | Result | Evidence                                          |
| ------------------------- | ------ | ------------------------------------------------- |
| Prettier formatting       | PASS   | All matched files formatted                       |
| ESLint                    | PASS   | Zero warnings                                     |
| TypeScript                | PASS   | Frontend, tests and build configuration           |
| Ruff formatting           | PASS   | Both Python files formatted                       |
| Ruff lint                 | PASS   | No findings                                       |
| mypy                      | PASS   | Strict checking, two source files                 |
| Python tests              | PASS   | 2 tests                                           |
| rustfmt                   | PASS   | Native sources formatted                          |
| Repository baseline tests | PASS   | 3 tests                                           |
| Frontend tests            | PASS   | 1 DOM test                                        |
| Frontend build            | PASS   | Vite production assets generated                  |
| Rust check                | PASS   | All targets checked with locked dependencies      |
| Rust Clippy               | PASS   | All targets, warnings denied                      |
| Rust test target          | PASS   | Compiled and executed; 0 tests in the empty shell |
| Tauri executable build    | PASS   | Release executable built with locked dependencies |

The production frontend contains HTML, local CSS and a 222.71 kB JavaScript
bundle (69.39 kB gzip). The native release executable is
`apps/desktop/src-tauri/target/release/mediaqc-desktop.exe`.
Full gate output is retained locally in `.cache/phase0-native-ready-check.log`;
individual native reruns are in `.cache/aligned-*.log`.

The earlier missing-linker blocker is resolved. Tauri 2.10.3 then exposed an
`E0308` incompatibility with the locked Tauri 2.11 runtime packages. Pinning
`tauri = 2.11.5` and `tauri-build = 2.6.3`, and regenerating Cargo.lock,
resolved it without application source changes. The existing locked native
check, Clippy, test-target and release-build commands reproduce and guard against
this dependency compatibility failure; no artificial application test was added.

No remaining gate failure was observed. Interactive window launch and installer
testing were not performed in this check-only rerun. Installer/clean-machine
testing remains in Phase 9. The specification package remains unchanged.

Local toolchain environment used for this validation (process-local only):

```powershell
$env:UV_CACHE_DIR = Join-Path $PWD '.cache/uv'
$env:CARGO_HOME = Join-Path $PWD '.tools/cargo'
$env:RUSTUP_HOME = Join-Path $PWD '.tools/rustup'
$env:PATH = (Join-Path $PWD '.tools/bootstrap/bin') + ';' + (Join-Path $PWD '.tools/cargo/bin') + ';' + $env:PATH
```

## Issues resolved during bootstrap

- Sandbox network restrictions required approved registry/install retries.
- Sandbox access to uv's locally installed files required checks to run with
  permission to access that tool directory.
- jsdom 30 required a newer Node patch; jsdom 28 supports the selected runtime.
- ESLint 9 was deprecated; the final manifest uses supported ESLint 10.
- Vitest 5's published declarations failed strict checks. The final compatible
  Vite 7/Vitest 4 versions include the available advisory fixes. No compiler
  checks were suppressed, and `skipLibCheck` remains disabled.
- Test declarations require the `ESNext.Disposable` type library; it is included
  explicitly. This does not add a runtime polyfill or application behavior.
- An unnecessary jest-dom matcher dependency was removed; the test performs
  the same DOM assertions through Vitest and the DOM API.
- The final lockfile resolves esbuild 0.28.2 within Vite's supported dependency
  range. The final `npm ci` audit reports zero known vulnerabilities.
- Tauri's icon generator warned about two installed Source Sans Pro font files.
  The icon SVG uses only paths and a rectangle, so it has no font dependency.

## Files and commands

The full structure and command expansions are in [DEVELOPMENT.md](DEVELOPMENT.md).
[PHASE_0_COMMANDS.md](PHASE_0_COMMANDS.md) records every dispatched PowerShell
invocation, including failed attempts and retries. The final source-control
summary is reported with task completion. No existing tracked file was modified;
all implementation files are new and uncommitted.

New files (44 total):

```text
.editorconfig
.gitignore
.node-version
.npmrc
.prettierignore
.python-version
apps/desktop/package.json
apps/desktop/src-tauri/Cargo.lock
apps/desktop/src-tauri/Cargo.toml
apps/desktop/src-tauri/build.rs
apps/desktop/src-tauri/icons/icon.ico
apps/desktop/src-tauri/icons/icon.png
apps/desktop/src-tauri/src/main.rs
apps/desktop/src-tauri/tauri.conf.json
apps/frontend/index.html
apps/frontend/package.json
apps/frontend/src/App.tsx
apps/frontend/src/main.tsx
apps/frontend/src/styles.css
apps/frontend/tests/App.test.tsx
apps/frontend/tests/setup.ts
apps/frontend/tsconfig.json
apps/frontend/tsconfig.node.json
apps/frontend/vite.config.ts
config/app-icon.svg
config/prettier.json
docs/DEVELOPMENT.md
docs/PHASE_0.md
docs/PHASE_0_COMMANDS.md
engine/src/mediaqc_engine/__init__.py
engine/src/mediaqc_engine/py.typed
engine/tests/test_package.py
eslint.config.mjs
package-lock.json
package.json
pyproject.toml
rust-toolchain.toml
tests/fixtures/generated/.gitkeep
tests/fixtures/manifests/.gitkeep
tests/golden/.gitkeep
tests/repository.test.mjs
tools/check.mjs
tools/generate_test_media/.gitkeep
uv.lock
```

No cloud dependency, Redis, PostgreSQL, Celery, local backend, Docker runtime or
external developer-tool requirement for the eventual end user was introduced.
