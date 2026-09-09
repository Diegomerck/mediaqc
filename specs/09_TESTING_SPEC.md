# 09 — Testing and Validation Specification

**Version:** 1.0.0

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
