# Phase 12 — duplicate/cadence investigation

Status: **correction unresolved; acceptance gate is failing**. No production
detector, detector version, profile, persisted finding, disposition, or verdict
was changed in this targeted increment. The new tests intentionally assert the
required clean outcomes and currently fail. They are not xfailed or skipped.

The [2026-09-27 temporal follow-up](PHASE_12_TEMPORAL_CONTEXT.md) extends this
evidence without regenerating the retained corpus. It documents temporal
counterexamples, additional positive/negative cases, and the missing expectation
signal needed to distinguish authored holds from observationally identical faults.

## Root cause

`video.duplicate_frame` and `video.frame_cadence` both call the same `repeats()`
state machine. It interprets RGB similarity above the profile threshold as a
repeat, with a frame-difference threshold on either side as cadence evidence.
Neither the candidate's residual structure nor an independent content-cadence
model is examined. A cut also satisfies that surrounding-motion check.

For the reviewed MP4, both detectors report 2.565944–2.599256 s. The minimum
pair similarity is 0.9990257353 against 0.999; surrounding motion is 0.0160833113
against 0.015. It therefore passes every existing gate. This is an algorithmic
specificity gap: similar images bracketed by change do not establish unintended
repetition. The owner's zoom annotation remains authoritative negative ground
truth. There is no filename, timestamp, or review-disposition exception in code.

The finding's `difference` and `hash_similarity` fields originate from the first
frame's comparison with its predecessor, not the near-repeat pair. Investigation
must use adjacent decoded frames or cache rows, and `similarity_statistic`, rather
than mistake those first-frame fields for pair evidence. This metadata issue was
identified but not changed in this increment.

## Approaches tested and rejected

Read-only excerpts used the production `-noautorotate`, RGB24, 320×180 area-scale
measurement geometry. Diagnostic arrays were short, bounded excerpts. No source
images were logged, and all generated media/report outputs stayed in ignored
project cache directories.

- **Exact decoded equality:** would remove the reviewed near-repeat, but fails a
  genuine single copied frame after H.264 CRF 18 YUV420p encoding. That positive
  decodes with similarity 0.9994146242, not 1.0. The new test explicitly verifies
  a nonzero decoded pair difference as well as identical pre-encode images.
- **Residual smoothing/coherence:** block-mean residual energy did not separate
  the reference from genuine compressed copies. In diagnostic re-encodes of the
  existing lossless duplicate fixture, normalized 8×8 block residual energy was
  about 0.0346 for the reference and 0.0866–0.1237 for the first copied pair at
  CRF 23/18. A simple spatial-coherence veto would reject real defects too.
- **Small affine motion inferred from image gradients:** an in-sample fit can
  explain some residual in both reference and encoded copies. Predicting one
  spatial quadrant from the other three did explain the independent synthetic
  zoom, but failed on three of four reference quadrants (negative explained
  energy). This does not substantiate coherent geometric motion in that decoded
  pair, even though the owner's production intent is established. In-sample
  motion scores alone would be an unsupported basis for suppressing it.

These are rejected exploratory feature models, not calibrated algorithms or
proof that discrimination is impossible. No numeric result above became a policy
threshold or production constant. A safe correction has **not** been established;
tightening similarity, requiring more repeats, or suppressing all near-repeats
would trade away defect coverage without resolving the underlying ambiguity.

## Acceptance additions

`tests/fixtures/manifests/video_repeats.json` is a direct correctness gate for the
two detectors with General Technical QC 1.2.0 and no overrides. Expected findings
include exact severity, stream index, frame count, and 1 µs timestamp tolerance
on these generated 25 fps timelines. New recipes are generator version 1.2.0;
the earlier fixture recipes and expected outputs were retained.

| Case                                             | Required outcome                         | Current result          |
| ------------------------------------------------ | ---------------------------------------- | ----------------------- |
| Independently rendered zoom with a near-repeat   | No findings                              | **FAIL**, both findings |
| Same zoom, lossy H.264                           | No findings                              | PASS                    |
| Continuous low-motion subpixel translation       | No findings                              | PASS                    |
| Full static shot                                 | No findings                              | PASS                    |
| Two-frame static insert between hard cuts        | No findings                              | **FAIL**, both findings |
| Single inserted copied frame, lossless           | Both findings, 2 frames                  | PASS                    |
| Single inserted copied frame, lossy H.264        | Both findings, 2 frames                  | PASS                    |
| Two inserted copied frames, lossy H.264          | Both findings, 3 frames                  | PASS                    |
| Four periodic inserted repeats on a CFR timeline | Four events per detector                 | PASS                    |
| Six held frames / 0.24 s                         | Both findings                            | PASS                    |
| Seven held frames / 0.28 s                       | Outside the existing brief-repeat policy | PASS                    |
| Repeat at EOF without following motion           | Insufficient context; no findings        | PASS                    |

The last two cases assert existing policy abstention, not clean media. The
periodic case injects broken content cadence while preserving PTS; this is not a
claim to detect every dropped-frame, telecine, VFR, or frame-rate-conversion fault.
Legitimate cadence conversions and independent real-world holdout footage still
need coverage before a general cadence model is accepted.

## Focused validation

```powershell
.venv/Scripts/python.exe tools/detector_acceptance.py tests/fixtures/manifests/video_repeats.json --output .cache/phase12/repeat-investigation-report.json
.venv/Scripts/python.exe -m pytest engine/tests/test_video_repeats.py engine/tests/test_video.py engine/tests/test_acceptance.py -k 'repeat or negative_motion or positive_copy or cadence_injection or long_static_sequence or current_profile_document' -q
.venv/Scripts/python.exe tools/reference_review.py .cache/phase12/repeat-reference-review.local.json --replay-negatives --output .cache/phase12/repeat-reference-replay.json
```

- Standalone manifest: **10 PASS, 2 FAIL**, exit 1.
- Focused pytest: **19 passed, 2 failed, 81 deselected**. Failures are precisely
  zoom settling and the static insert. Existing similarity-boundary tests, the
  bounded 200,000-frame state test, and the pinned profile hash pass.
- Fresh full-timeline original MP4 replay, scoped only to duplicate/cadence:
  both detectors COMPLETED; both still fail the reviewed zoom window. Neither
  reports in the reviewed exposure window. Full source hash/size/mtime verified
  unchanged. The original saved database was read only; its old verdicts remain.
- Ruff lint/format and strict mypy for the changed Python files pass.

The local scoped reference manifest is a copy of the original review manifest
with only its negative-window detector lists narrowed. It retains original
paths, identity, intent, profile, and historical review annotations. Reports
retain observations/provenance; annotations do not suppress fresh findings.

Runtime bounded-memory decoding, shared disk cache, subprocess ownership,
cancellation, and Phase 10 safeguards are untouched. No full quality gate,
Windows build, packaging, commits, pushes, merges, or PRs were performed.

The next correction must pass both failing negatives and all positive cases.
Longer temporal motion/cut context and codec-aware evidence need an independently
validated decision rule; the current experiments do not justify one. This
increment leaves that limitation visible for review instead of claiming a fix.
