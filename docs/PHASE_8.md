# Phase 8 — Optional embedded local AI

The default remains OFF. LOCAL is selectable only when the engine reports an
installed compatible embedded provider/model. This phase ships the abstraction
and pipeline, without a production model or heavyweight runtime. No service,
model manager, network, account, telemetry, or download is required. Production
runtime/model selection and bundling are explicitly deferred to Phase 9.

## Implementation

- `engine/src/mediaqc_engine/ai.py`: trusted embedded adapter contract, bounded
  compatibility/review worker process, evidence allowlist, strict output validation,
  warning diagnostics and nonfatal failure handling. Python audit hooks reject
  socket/network and child-process operations in the worker; adapters must also
  prohibit native-library networking. This is defense in depth, not an OS sandbox.
- OFF never probes or invokes the provider during analysis. LOCAL accepts a model
  disappearing between capability selection and execution and persists unavailable
  review while completing deterministic QC. Retries preserve the selected mode.
- Input is copied saved measurements/thresholds, detector identity, finding ID and
  deterministic interval, and up to three verified Phase 6 PNGs. Source paths,
  source media bytes, file tags, operator notes and unrelated project data are not
  supplied. No provider receives a database connection. Measurements-only review
  is permitted where no PNG references exist; missing/stale referenced PNGs fail
  the optional review explicitly.
- Compatibility: 3 seconds. Review: 30 seconds each, 120 seconds total, at most 20
  findings, sequential. Input: 1200 KiB. Output: 8 KiB and 512 requested tokens.
  Workers are terminated/reaped on completion, crash, cancellation or timeout.
  Future runtime adapters must enforce their model/context memory budgets.
- Migration 002 adds separate `ai_reviews` storage with relational provenance,
  status/error fields, structured output and UTC creation time. Version 1 migration
  validates the canonical schema, retains a SQLite backup (including committed
  WAL state), and rolls back on failure. Existing raw records are unchanged.
- Existing finding IPC returns optional advisory review data. The analysis form
  shows OFF/LOCAL and model status; the inspector shows advisory text, confidence,
  classification, recommendation, model/template provenance and evidence refs.
  No AI recommendation changes disposition. Unreviewed or failed AI is explicit.
- Existing deterministic report exports remain unchanged. No detector, threshold,
  severity, event timestamp, evidence, overall-result rule or architecture dependency
  is changed. Specs 03/06/07/08 contain only the approved Phase 8 reconciliation.

## Verification

Focused Python tests use deterministic embedded fake adapters and real saved
Phase 6 audio/video evidence. They cover available/missing/incompatible models,
OFF bypass, runtime errors, timeout/cancellation and worker reaping, malformed or
oversized output, strict schema validation, attempted network access, input and
review limits, evidence-only input, missing artifacts, persistence failures,
reopen, migration rollback/backup, immutable findings/evidence/source files,
PASS/WARN/FAIL preservation and retry with an unavailable model.

Frontend tests cover capability-gated LOCAL, default OFF, failed capability checks,
advisory display, explicit unavailable review and unchanged deterministic output.
Existing Phase 0–7 regressions are retained; version-specific assertions now use
schema 2, additive AI capability fields, and reject CLOUD rather than LOCAL.

Packaged engine smoke verifies unavailable AI and schema 2. The existing packaged
audio smoke additionally runs LOCAL without a provider, compares deterministic
measurements, thresholds, severity and timestamps against OFF, checks COMPLETED
and identical overall result, and verifies separate unavailable-review persistence
across restart. Existing source hash/mtime assertions remain in force.

## Recorded validation — 2026-09-19

Exact Phase 8 exit criteria:

- PASS: app works identically with AI disabled. OFF bypass tests, existing Phase
  0–7 regressions, UI tests and packaged deterministic comparisons preserve
  measurements, thresholds, timestamps, severity, disposition and PASS/WARN/FAIL.
- PASS: AI failure cannot fail deterministic analysis. Fake failures, malformed
  output, unavailable models, timeouts and persistence failures are isolated.
  Packaged LOCAL without an installed model completes with the same deterministic
  result as OFF and preserves unavailable AI review separately across restart.

Focused Phase 8 coverage: **63 passing tests** (57 engine, 6 new UI).
The corrected engine test file passed **57/57** using the exact gate launcher,
`uv run --locked pytest engine/tests/test_ai.py -q`.

The full `npm run check` ran **once**, attempting all 22 gates: 20 initially passed,
and two required targeted corrections. The original log is
`.cache/phase8-quality-gate.log`.

1. Formatting flagged three pre-existing Phase 7 files: `ReportExport.tsx`,
   `ReportExport.test.tsx` and `PHASE_7.md`. Mechanical Prettier normalization
   leaves no Git content diff in those files and changes no Phase 7 behavior.
2. Python tests initially passed 279/288. Nine AI tests failed because console
   pytest's spawned workers could not import `engine.tests.test_ai`, which held
   the fake provider. A temporary launcher diagnostic confirmed
   `ModuleNotFoundError: No module named 'engine'`. The unchanged fake adapter now
   lives in `tools/ai_test_adapter.py`, on the existing configured test import
   path. No assertions or production code were weakened or changed by this fix.
   All 57 AI tests passed through the gate launcher after the move. The rerun log
   is `.cache/phase8-ai-launcher-validation.log`.

Unique repository test totals across the original full run and targeted correction:
**346 passing** = 288 Python + 39 frontend + 16 Rust + 3 repository tests.
The six new UI tests are included in the 39 frontend tests. Temporary diagnostic
probes and packaged smoke scenarios are not counted as repository tests.

Windows Tauri optimized release build: PASS, producing
`apps/desktop/src-tauri/target/release/mediaqc-desktop.exe`.
Packaged standalone engine, native lifecycle, projects, jobs, audio and MP4/MXF
video smokes: PASS. The audio smoke includes the Phase 8 OFF/LOCAL comparison,
unavailable model handling, immutable deterministic fields and AI persistence
across restart. Source SHA-256/mtime checks pass; focused fixtures also verify
unchanged evidence bytes and no source-adjacent files. These successful builds
and smokes were not repeated after the test-only adapter relocation.

No dependency or lockfile change, cloud service, account, telemetry or downloader
was introduced. The gate used existing caches with `UV_OFFLINE=1` and
`CARGO_NET_OFFLINE=true`; tests block socket use and verify worker network attempts
fail. Clean-machine installation, firewall-enforced offline execution, manual
native UI review and a real production model are not validated. Runtime/model
licensing, distribution, hardware suitability and native-library memory/network
controls remain explicit future provider/bundling decisions.

Final targeted commands (no second full gate):

```powershell
uv run --locked pytest engine/tests/test_ai.py -q
uv run --locked ruff format --check engine/tests/test_ai.py tools/ai_test_adapter.py
uv run --locked ruff check engine/tests/test_ai.py tools/ai_test_adapter.py
uv run --locked mypy
npm run format:check
git diff --check
```

The final targeted static-check log is `.cache/phase8-correction-checks.log`.
All changes remain uncommitted on `phase/08-local-ai`.
No Phase 9 installer, production model bundling or performance work is implemented.
