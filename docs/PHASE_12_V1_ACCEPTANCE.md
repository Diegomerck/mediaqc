# Phase 12 V1 acceptance disposition — implemented

The user-approved V1 disposition is now implemented as a developer-only release
assessment. This supersedes the release-blocking conclusion of the
[previous review](PHASE_12_ACCEPTANCE_REVIEW.md), not its measurements, ground truth,
rejected approaches or documented limitations. Production signal processing,
detector thresholds/versions, General Technical QC 1.2.0, runtime findings and
historical verdicts are unchanged.

## Two independent results

`tools/detector_acceptance.py` still computes and preserves the strict `status`
(PASS/FAIL), errors, original expectations and complete observation. Its default
CLI still exits nonzero for any ground-truth failure. Optional `--release` adds a
separate release assessment; it never replaces FAIL with PASS or modifies the
original manifest. Multiple explicitly supplied manifests can share one report.

The release states are:

- `REQUIRED_PASS`: unregistered case satisfies strict correctness requirements.
- `ACCEPTED_LIMITATION`: exact approved known detector limitation, still carrying
  its ground-truth FAIL and errors.
- `ACCEPTED_EXPECTATION_LIMITATION`: approved unavailable-intent contradiction,
  likewise retaining ground truth and the mismatch.
- `NEEDS_INDEPENDENT_EVIDENCE`: separate unresolved reference review, never a
  finding exception or a claim of freshly measured media.
- `REGRESSION`: unregistered mismatch, changed bound behavior, execution error or
  skipped/failed execution; blocking.
- `REVIEW_REQUIRED`: changed case/generator/profile/detector/tool binding, or an
  apparent improvement in a registered case; blocking until explicitly reviewed.

The release report and console show ground-truth failures, accepted limitations,
release blockers, unexercised limitation IDs and the unresolved reference. A
partial selection does not claim coverage of unexercised cases. Full validation
and false-positive budgets are not implied by an empty blocker count here.

## Exact registry and safety boundaries

The reviewed records live in `tests/fixtures/phase12_limitations.json`, schema
1.0.0, with approval provenance and links to the investigation evidence. The
reader is limited to 1 MiB and 32 records; the approved-inventory regression test
requires exactly the current twelve IDs. Duplicate entries, unknown record fields,
invalid bindings and failed execution baselines are rejected.

Each exception binds to:

- SHA-256 of the entire original case document, including annotations, expected
  findings, generator version, detector selection and any profile overrides;
- generator source SHA-256;
- complete effective profile snapshot digest and exact detector versions;
- bundled-tool provenance digest;
- all stable findings, measurements, confidence, timing, severity, stream identity,
  thresholds, metadata, metrics, execution states, errors and warnings.

Only generated finding UUIDs and collection ordering are excluded from behavior
comparison. There is no numeric tolerance added to the exception envelope and no
wildcard detector/filename/time/category exemption. Existing strict positive
fixture tolerances are unchanged. The two existing zoom manifests have separate
explicit case digests in one record; no new annotation variant is implicitly
accepted. Registry edits require review; no refresh/update-baseline command is
provided. Changed execution failures cannot be excused even by a registered ID.

No engine module imports this developer registry. It cannot suppress production
findings, classify source intent, change INFO/WARN/FAIL or change saved history.

## Final approved dispositions

The names below abbreviate the unchanged fixture IDs ending in `.001`.

| Case                                | Classification                      | Accepted limitation or decision                                                |
| ----------------------------------- | ----------------------------------- | ------------------------------------------------------------------------------ |
| audio `masked`                      | Known detector limitation           | Explicit missed-defect/recall limitation from shared cross-channel baseline    |
| audio `masked_swapped`              | Known detector limitation           | Same accepted missed defect with channel order reversed                        |
| audio `sharp`                       | Known detector limitation           | Legitimate sharp attack false positive                                         |
| audio `sharp_stereo`                | Known detector limitation           | Simultaneous legitimate attack false positive                                  |
| audio `sharp_delayed`               | Known detector limitation           | Delayed legitimate attack false positive                                       |
| audio `sustained_shifted`           | Known detector limitation           | Window-position-dependent legitimate attack false positive                     |
| audio `mxf_sharp`                   | Known detector limitation           | Legitimate attacks on independent mono streams flagged                         |
| video `zoom_settle`                 | Known detector limitation           | Near-repeat during independently rendered zoom flagged                         |
| video `static_between_cuts`         | Known detector limitation           | Legitimate static insert flagged using surrounding cuts                        |
| video `intentional_hold`            | Acceptance/test expectation problem | Same input as fault-labelled counterpart cannot yield opposite inferred intent |
| video `intentional_hold_lossy`      | Acceptance/test expectation problem | Same contradiction after lossy encoding                                        |
| video `intentional_periodic_hold`   | Acceptance/test expectation problem | Same contradiction for authored periodic holds                                 |
| Original MXF transient near 7.567 s | Needs independent evidence          | Nonblocking unresolved review; neither clean nor confirmed defective           |

The two missed clicks are known defects and explicit accepted recall risk, not
uncertain ground truth or proof of unavoidable ambiguity. All clean-content labels
remain clean. No original reference or historical reference DB was opened or
replayed to implement these dispositions.

For all three authored-hold pairs, real generated encoded source hashes and
complete stable detector observations must match their positive counterparts.
Their opposite causal annotations, strict positive PASS and negative ground-truth
FAIL remain tested. These equal-input consistency tests complement, rather than
replace, the earlier full-image/PTS identity counterexamples.

## Focused verification

Mutation tests require blocking for changed case identity/annotation/generator
version, profile/threshold, detector scope/version, tool provenance, missing/new
metrics, extra findings, wrong stream/severity/timing/measurements/confidence,
execution errors/skips and new warnings. An unregistered masked-click miss still
fails. Invalid/duplicate/oversized registries fail closed. CLI tests verify default
strict failure versus explicit release success while preserving visible FAIL and
unresolved-reference reporting. Apparent improvements require review, never an
automatic baseline replacement.

The applicability and report implementation is unchanged. Its focused suite covers
required versus unused/unknown channel silence, the 1.0.1 EOF correction retained
in 1.1.0, declared program/ISO routing, raw evidence, retry/reopen, full source hash
validation, schema/history preservation, and complete saved assignment context in
HTML/PDF. Desktop assignment editing and batch propagation remain outside scope.

Commands for this checkpoint:

```powershell
.venv/Scripts/python.exe -m pytest engine/tests/test_acceptance_disposition.py engine/tests/test_acceptance.py engine/tests/test_audio_calibration.py engine/tests/test_video_repeats.py engine/tests/test_video_temporal_context.py engine/tests/test_audio_runtime.py engine/tests/test_audio_program_clock.py engine/tests/test_audio_applicability_contract.py engine/tests/test_discontinuity_shape_probe.py engine/tests/test_discontinuity_identifiability.py engine/tests/test_reports.py -q --tb=short
.venv/Scripts/python.exe tools/detector_acceptance.py tests/fixtures/manifests/audio_discontinuity.json tests/fixtures/manifests/audio_applicability.json tests/fixtures/manifests/video_repeats.json tests/fixtures/manifests/video_temporal_context.json --release --output .cache/phase12/v1-release-disposition.json
```

Final focused pytest result: **277 passed**. Ruff lint/format and strict mypy
pass for all six changed Python files. All **3** repository/specification checks,
documentation/registry formatting and `git diff --check` pass.

The combined report exercises 42 scoped cases (30 strict PASS, 12 strict FAIL),
including all twelve approved limitation IDs. It retains
**12 ground-truth failures, 12 approved dispositions, zero release blockers and no
unexercised limitation IDs**. The original MXF review is explicitly unresolved.
No full quality gate, Windows build, packaging, commit, push, merge or PR was run.
Phase 12 is ready to request final full-quality-gate validation after this focused
checkpoint; that readiness is not a claim that full validation or release is done.
