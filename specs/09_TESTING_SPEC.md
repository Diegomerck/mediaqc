# 09 — Testing and Validation Specification

**Version:** 1.1.0

## 1. Testing philosophy

A detector is not "working" because it produces plausible output on one file.

V1 requires a repeatable golden QC corpus with known injected defects and clean controls.

## 2. Test layers

### Unit tests
Pure math/parsing/profile logic.

### Integration tests
Engine + FFmpeg/ffprobe + SQLite + filesystem.

### Detector fixture tests
Known defect media.

### Regression tests
Every fixed bug.

### UI tests
Critical workflows.

### Packaging tests
Clean Windows install and offline operation.

### Performance tests
Memory, runtime, process cleanup.

## 3. Synthetic fixture generator

Repository SHALL contain developer tooling capable of creating short deterministic media fixtures using FFmpeg/Python.

Suggested structure:

```text
tests/
  fixtures/
    manifests/
    generated/
  golden/
tools/
  generate_test_media/
```

Generated binary fixtures MAY be excluded from Git if reproducibly generated during test setup.

## 4. Fixture manifest schema

Example:

```json
{
  "fixture_id": "video.freeze.001",
  "generator_version": "1.0.0",
  "file": "freeze_001.mp4",
  "duration_seconds": 10.0,
  "expected_findings": [
    {
      "detector_id": "video.freeze",
      "severity_min": "INFO",
      "start_time_seconds": 4.0,
      "end_time_seconds": 5.0,
      "timestamp_tolerance_seconds": 0.08
    }
  ],
  "forbidden_findings": [
    {
      "detector_id": "video.black_frame"
    }
  ]
}
```

## 5. Required audio fixtures

At minimum:

- `audio.clean.001`
- `audio.clipping.001`
- `audio.true_peak.001`
- `audio.silence.001`
- `audio.dropout.short.001`
- `audio.discontinuity.001`
- `audio.hum.50.001`
- `audio.hum.60.001`
- `audio.noise_floor.001`
- `audio.channel_imbalance.001`
- `audio.phase_negative.001`

For each defect fixture:
- known insertion time;
- known duration;
- known amplitude/frequency parameters where relevant.

## 6. Required video fixtures

At minimum:

- `video.clean.001`
- `video.black.001`
- `video.near_black.001`
- `video.freeze.001`
- `video.duplicate.001`
- `video.flash.001`
- `video.luma_anomaly.001`
- `video.timestamp_irregularity.001`
- `video.decode_corrupt.001` if reproducibly constructible;
- `video.visual_anomaly.001`.

## 7. Timestamp tolerances

Initial V1 target:

- audio event detectors: <= 50 ms unless windowing algorithm makes tighter impossible and documented;
- video event detectors: <= max(1 frame, 50 ms);
- whole-program metrics: numeric tolerance specified by detector test.

Do not use exact floating-point equality for timestamps/metrics.

## 8. Clean corpus

Synthetic clean files alone are insufficient.

Maintain a small curated clean corpus representing:
- talking head;
- music;
- quiet dialogue;
- static shots;
- slow camera moves;
- hard cuts;
- fades;
- black leader/slate where expected;
- stereo and mono audio.

Expected result depends on profile, but generic anomaly detectors must have a false-positive budget.

## 9. False-positive budget

For `general_technical_qc` on curated clean corpus:

- deterministic integrity/threshold detectors: zero unexplained false positives;
- heuristic audio dropout/discontinuity: target <= 1 false WARN per 30 minutes;
- heuristic visual anomaly/flash/freeze: target <= 1 false WARN per 30 minutes of representative clean content.

These are initial engineering targets and may be amended based on corpus growth.

## 10. Detector regression gate

A detector change cannot merge if it:

- worsens required fixture recall;
- exceeds false-positive budget;
- changes numeric measurement outside documented tolerance;
- breaks evidence generation;
- materially worsens performance without justification.

## 11. IPC tests

Required:

- framing;
- malformed JSON;
- unknown method;
- request correlation;
- Unicode paths;
- cancellation;
- engine unexpected exit;
- stderr noise does not affect protocol.

## 12. Database tests

Required:

- schema creation;
- migration;
- foreign keys;
- profile snapshot immutability;
- disposition history;
- project reopen;
- interrupted run recovery.

## 13. Source immutability test

For every integration fixture:

1. hash source before run;
2. execute inspection + analysis + report;
3. hash source after run;
4. hashes MUST match.

## 14. Offline test

On clean Windows validation machine:

- disconnect network or block outbound connections;
- install;
- launch;
- create project;
- analyze;
- inspect findings;
- export report.

No required feature may fail due to network.

## 15. Process cleanup test

Start long analysis, cancel it, then assert:
- run = CANCELLED;
- engine remains usable;
- no orphan owned FFmpeg/ffprobe process remains.

Also test closing app during analysis.

## 16. Large-file test

Use a large sparse/long media fixture or representative real file.

Assert:
- memory usage remains bounded;
- no full-file copy into project;
- cancellation works;
- disk cache behavior documented.

## 17. Windows matrix

Minimum validation:

- Windows 11 current supported release;
- Windows 10 supported release where technically compatible;
- CPU-only machine;
- NVIDIA machine optional for acceleration tests;
- non-admin user installation/use where installer design permits.

## 18. Definition of detector done

A detector is V1-ready when:

- algorithm documented;
- profile fields documented;
- unit tests pass;
- synthetic positive fixtures pass;
- clean negative fixtures pass budget;
- evidence exists;
- failure/cancellation tested;
- performance is acceptable.

## 19. Phase 10 acceptance matrix

These are implementation/release exit requirements, not claims of completed tests.
The specification-only amendment does not authorize running the full quality gate
or building packages. Implement focused regression tests alongside each approved
implementation step, then perform release validation when authorized.

| Area | Required evidence |
|---|---|
| Single file | One-item batch and legacy single-run APIs preserve metadata, detector versions/measurements, findings, evidence, verdict/disposition rules, notes, and detailed HTML/PDF output. Compare semantic results excluding generated IDs/timestamps. |
| Formats | Real mixed WAV/MP3/MP4/MXF fixture batch completes supported analyses. Automatic extension matching is case-insensitive and exactly the documented four extensions. MOV/AIFF/AIF/FLAC/AAC and renamed unsupported extensions are not auto-admitted merely because FFmpeg can decode them. Explicit single-file selection retains probe-based behavior. |
| Folder import | Default excludes subdirectories; optional recursion includes ordinary descendants. No symlink/junction/reparse traversal, including a selected linked root; no loops. Stable order and membership after discovery. Empty folder disables Start. |
| Exclusions and duplicates | Unsupported files/project artifacts are inspectable and excluded from processing totals. Normalized duplicate paths produce one queue item and visible duplicate count; same basename/different paths and same-content/different paths remain distinct. New batches preserve earlier run history. |
| Unreadable/corrupt input | Unreadable root fails discovery; inaccessible child directory yields prominent partial-import warning. Supported unreadable/corrupt files become ERROR with null verdict and actionable diagnostics; later safe files run. Changed/missing sources are never silently accepted. |
| 137-file queue | Stable ordering, correct totals, exactly one active file including inspection/evidence, no pre-created queued run per pending item. Combine deterministic coordinator doubles for race tests with a real 100+ short-file integration batch. |
| Pause/Resume | Pause during inspection/analysis/evidence allows the current file to finish, starts no successor, preserves completed data and saved profile/AI mode. Pause between files is immediate. Last-file Pause ends COMPLETED. Repeated controls do not duplicate runs. |
| Stop | Stop at inspection, detector, evidence, and between-file boundaries persists cancellation and terminal events, reaps owned ffprobe/FFmpeg, cancels pending members without synthetic runs, and retains completed results. Stop file 127 of 150 and verify first 126 run/findings/evidence records after reopen. |
| Races/ownership | Exercise Stop versus terminal commit, Pause/Stop versus next claim, standalone Start/Retry/Cancel versus batch ownership, project switching, and export versus Resume. At most one worker/file is active; no deadlock or scheduling after accepted Stop. |
| Recovery | Inject termination after item claim, before/after atomic run creation/linkage, after run terminal commit before item update, and during STOPPING. Reconcile from DB without journal dependence for pending items. Completed runs win, interrupted runs fail, pending files require explicit continuation. No mid-file resume or automatic rerun. Interrupted discovery cannot continue. |
| Persistence/migration | Version 1→2→3 and 2→3, committed-WAL backup, rollback on failure, no overwritten backup/history, foreign keys, same-project links, immutable snapshots, original retry links, preserved old reports and notes. Reopen paused/completed/stopped batches and retry as new batches. |
| Filtering/counts | SQL filters span all pages; 50-row pages and stable ordering; NEEDS_ATTENTION = WARN/FAIL/ERROR. All partition counts sum to total, exclusions do not. Disposition changes update verdict/count/filter/revision atomically, including when the file leaves the current filter. |
| Progress | File-weighted formula, correct processed/current-file labels, indeterminate unknown progress, finalization before 100%, and explicit stopped coverage. Stale/duplicate/lost events and late subscriptions reconcile with compact snapshots. |
| Drill-down | No details/evidence fetched for unselected files/findings. Technical details collapsed initially; all diagnostics remain accessible. Evidence errors and execution errors stay visible. Timeline, dispositions, notes, and return-to-page/filter work. |
| Explanations | Persisted -24.12 LUFS against -23 ±1 produces bounds -24/-22 and 0.12 LU outside the lower bound. Test upper/lower boundaries, units, null/nonfinite protection, display rounding, historical profile edits, unknown schemas, and unchanged raw measurements/severity. No AI or UI analysis. |
| Reports | Existing per-run HTML/PDF remains valid. Batch HTML/PDF has one processing-member row per file, exact saved counts/revision/profile, separate exclusions, explicit incomplete states, offline reopen export, retained older artifacts, and cleanup on failure. No whole-batch evidence embedding. |
| Immutability | Compare source bytes/hash, size, modification time, names, and directory contents before/after import, QC, Stop, retry, disposition, and export; no output sidecars or source writes. Do not require unchanged OS-managed access time. |
| AI | Entire batch works with AI OFF; unavailable/failing LOCAL advice cannot fail deterministic QC. No new production provider/model/runtime. |
| Deployment | Both clean-machine NSIS and relocated portable ZIP pass the batch workflow offline, CPU-only, with bundled engine/FFmpeg/ffprobe and no developer tools. Honor documented WebView2 prerequisites. |

### Scalability and resource acceptance

- UI test with 1,000 stored item summaries mounts at most 50 batch rows and only
  one selected result view. Page/filter transitions fetch bounded summaries, not
  all analysis.get responses or source stat checks. Old previews are released.
- Bound discovery buffers and protocol payloads, including a large exclusion list;
  IPC remains responsive to Stop while scanning or probing. Poll requests never
  accumulate when an earlier poll is pending.
- Compare peak/steady engine, owned-child, and WebView memory on repeated short-file
  batches and representative long 1080p/4K/MXF files. Record hardware, codec, duration,
  working set, and cache/evidence disk growth. Queue persistence may grow on disk;
  decoded media and result/evidence buffers must not accumulate per processed file.
- Use structural tests for bounded page/stream buffers plus measured runs showing
  no sustained per-file memory growth after warm-up. Investigate deviations; do not
  invent a universal RAM ceiling unsupported by the target workstation baseline.
- Preserve Phase 9 detector/cancellation performance guarantees. No throughput
  optimization may change QC mathematics or profile sampling without amendment.

### Focused implementation order for validation

1. Migration/repository/state-machine and recovery tests.
2. Discovery/inspection/queue integration and cancellation races.
3. IPC/desktop ownership, compact reads, event reconciliation.
4. Dashboard/drill-down/explanation and report regressions.
5. Existing deterministic suites, 100+ real-file integration, scalability evidence.
6. Required quality gate and installed/portable release matrix only in an explicitly
   authorized implementation/release task, not during specification editing.
