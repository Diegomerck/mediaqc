# MediaQC — Project Commands & Workflow Reference

This document catalogs the authoritative terminal commands for developing, testing, building, and validating MediaQC, along with the strict workflow trigger conventions for this pair-programming environment.

---

## 1. Workflow Triggers & Execution Modes

| Trigger Keyword | Operating Mode | Allowed Actions | Execution Model |
| :--- | :--- | :--- | :--- |
| *(None / Default)* | **PLANNING** | Discussions, requirement clarification, read-only file/git checks, edge-case evaluations, architecture reviews. **NO file writes, NO builds/tests.** | Main Agent (Concise responses) |
| **`IMPLEMENTATION`** | **IMPLEMENTATION** | Editing/creating code files, executing builds, running tests, verifying quality gates. | Dispatched automatically to a subagent assessed as **Standard Tier** (`flash`) or **High Tier** (`pro`). |
| **`QUICK FIX`** | **QUICK FIX** | Single-line typo, version number update, isolated CSS adjustment. | Applied directly by the main agent without invoking a subagent. |

### Complexity Tiers for Subagents
- **Standard Tier (`Model: "flash"`)**: Small UI adjustments, 1–2 files, localized styling, isolated components.
- **High Tier (`Model: "pro"`)**: Multi-file refactors, engine DSP/CV algorithms, database schema changes, IPC message protocol updates, packaging scripts.
- **Expensive Models (e.g. Argon)**: Prohibited unless explicitly requested by name by the user.

---

## 2. Slash Commands

- `/compact`: Use when conversation history becomes long to condense context and reduce token consumption per turn.
- `/plan`: Use during complex architecture or multi-step design tasks.
- `/goal`: Use for autonomous, long-running validation tasks once explicitly approved.

---

## 3. Project-Specific Terminal Commands

All commands are executed from the repository root (`C:\Dev\MediaQC\mediaqc`).

### Bootstrap & Environment
```powershell
# Install Node dependencies
npm ci

# Sync Python virtual environment with locked dependencies
uv sync --locked

# Prepare bundled media tools (ffmpeg / ffprobe)
npm run media:prepare

# Fetch Rust crates
cargo fetch --locked --manifest-path apps/desktop/src-tauri/Cargo.toml
```

### Full Quality Gate (CI-Equivalent)
Runs all 22 quality checks (formatting, linting, typing, unit tests, frontend build, engine build, rust check, smokes):
```powershell
npm run check
```

### Code Formatting
```powershell
# Check formatting across all languages
npm run format:check
npm run python:format:check
npm run rust:format:check

# Apply formatting
npm run format
uv run --locked ruff format .
cargo fmt --all --manifest-path apps/desktop/src-tauri/Cargo.toml
```

### Linting & Static Analysis
```powershell
# TypeScript & JavaScript lint (ESLint, zero warnings)
npm run lint

# TypeScript typecheck
npm run typecheck

# Python lint (Ruff) & strict typecheck (mypy)
npm run python:lint
npm run python:typecheck

# Rust Clippy (zero warnings)
npm run rust:lint
```

### Test Suites
```powershell
# All JavaScript/TypeScript tests (baseline + frontend Vitest)
npm test

# Baseline repository boundary checks
npm run test:baseline

# React frontend tests only
npm run test:frontend

# Python engine tests (pytest)
npm run python:test

# Focused Python test run (example)
uv run --locked pytest engine/tests/test_audio.py -v

# Rust native unit & integration tests
npm run rust:test
```

### Desktop Application Development & Start
```powershell
# Prepare embedded assets (frontend build + PyInstaller engine build)
npm run desktop:prepare

# Launch Tauri desktop app in development mode
npm run desktop:start
```

### Release Build & Packaging
```powershell
# Build standalone Python engine runtime (PyInstaller into engine/dist/)
npm run engine:build

# Compile prepared Tauri release binary (without installer wrapper)
npm run desktop:build:prepared

# Package Windows NSIS installer (MediaQC_x.x.x_x64-setup.exe)
npm run release:installer

# Assemble portable release ZIP (dist/MediaQC-...-portable-x64.zip)
npm run release:portable

# Run automated release validation against extracted bundle
npm run release:validate
```

### Packaged Smoke Tests
```powershell
# Standalone engine IPC & 10,000-ping stress test
npm run engine:smoke

# Native desktop controller lifecycle & abrupt parent-death test
npm run native:smoke

# Phase 2 inspection & reopen smoke test
npm run phase2:smoke

# Phase 3 job manager & cancel smoke test
npm run phase3:smoke

# Phase 4 audio QC & reports smoke test
npm run phase4:smoke

# Phase 5 video QC & multi-stream smoke test
npm run phase5:smoke
```

### Detector Acceptance & Benchmarks
```powershell
# Run acceptance corpus tool with V1 release disposition filter
uv run --locked python tools/detector_acceptance.py tests/fixtures/manifests/audio_discontinuity.json tests/fixtures/manifests/audio_applicability.json tests/fixtures/manifests/video_repeats.json tests/fixtures/manifests/video_temporal_context.json --release --output .cache/phase12/v1-release-disposition.json

# Run benchmark script against extracted application folder
uv run --locked python tools/benchmark_release.py <path-to-extracted-app> --output <output-dir>
```

