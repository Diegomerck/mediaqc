# Phase 12 — acceptance corpus and calibration framework

This implementation establishes developer acceptance tooling before detector
calibration. Production algorithms, General Technical QC 1.2.0, historical
findings/dispositions/verdicts, UI, IPC and database schemas remain unchanged.
No new runtime dependencies, network access or media uploads are introduced.

## What the framework checks

`tools/detector_acceptance.py` runs the real probe/decode/detector paths against
small generated media, using an explicit detector scope and profile version.
Every finding in that scope must match exactly one expectation, including exact
severity, stream index, event times and optional numeric measurements. Extra or
missing events fail. Matching is one-to-one even when tolerance windows overlap.
Metric checks support nested numeric `{value, abs_tolerance}` values, explicit
nulls, and states such as `NO_GATED_AUDIO` or `INSUFFICIENT_QUIET_REGIONS`.
Skipped/failed executions cannot pass a negative assertion. NaN and infinity are
rejected. Unknown IDs, fields and missing severity/timing tolerance are errors.

Expected findings are exhaustive **within `detectors`**, not for detectors that
were not selected. An empty list means zero findings in that scope. A passing
insufficient-evidence assertion verifies correct abstention, not clean content.
Categories describe technical defects, profile compliance and intentional content;
they never filter findings. Explicit per-case profile overrides exercise nullable
or disabled rules without editing a distributed profile. Generator parameters in
the legacy manifests document their fixed recipes; they are not runtime knobs.

The original audio manifest now decodes the actual generated source, instead of
reading/requantizing it into a second WAV. Original fixture expectations remain.
The video runner consumes declared timing tolerances and exact severity. Current
detectors all have a positive manifest expectation, though this is not a claim of
complete real-world acceptance or calibrated false-positive rates.

Fixtures remain short (normally 4 s video / 6 s audio; the LRA case is 20 s).
Temporary sources, derived caches and reports belong in ignored directories.
Source SHA-256, size and mtime are checked before/after execution, PCM caches are
cleaned, and owned processes are reaped even on failure. No reference binaries
or extracted source content are committed or logged.

## Coverage and remaining calibration work

The [audio calibration follow-up](PHASE_12_AUDIO_CALIBRATION.md) records the
subsequent discontinuity corpus, explicit L/R reference measurements, and
silence/applicability limitations. Production algorithms remain unchanged; the
new audio gates expose failures that require another targeted step.

| Detector                  | Positive manifest              | Negative/control evidence                    | Remaining priority                                               |
| ------------------------- | ------------------------------ | -------------------------------------------- | ---------------------------------------------------------------- |
| audio.loudness.integrated | Loud tone                      | Clean tone, digital silence                  | Defined L/R versus multitrack aggregate; reference program scope |
| audio.loudness.short_term | Explicit upper bound           | Null bounds and short-file unit cases        | Lower bound/window timing variants                               |
| audio.loudness.momentary  | Explicitly enabled upper bound | Null bounds and short-file unit cases        | Default disablement, lower bound                                 |
| audio.loudness.range      | Two-level 20 s program         | Constant tone, nullable bounds               | More gating/distribution cases                                   |
| audio.true_peak           | Intersample overs              | Clean tone, short/tail unit cases            | Codec/sample-rate numeric references                             |
| audio.sample_peak         | Known 0.999-amplitude tone     | Clean tone, equality unit case               | Float/24-bit and channel variants                                |
| audio.clipping            | Full-scale segment             | Clean tone, count/grouping unit cases        | Intentional limiting/square waves                                |
| audio.silence             | Internal 2 s gap               | Clean tone, edge/pair unit cases             | Fractional EOF and assigned unused streams                       |
| audio.noise_floor         | Seeded broadband noise         | Tonal/silent insufficient-evidence cases     | Representative quiet dialogue/room tone                          |
| audio.hum                 | 50/60 Hz families              | Tone, persistence unit cases                 | Bass/drone negatives                                             |
| audio.channel_imbalance   | 20 dB pair difference          | Balanced L/R with unequal ISOs               | Cross-stream applicability                                       |
| audio.phase_correlation   | Inverted pair                  | Balanced L/R, silence/mono unit cases        | Natural stereo/microphone negatives                              |
| audio.dropout             | Injected 20 ms gap             | Clean/percussive signal, duration unit cases | Intentional gating and window phase                              |
| audio.discontinuity       | Inserted impulse               | Continuous percussive attack/decay           | Wider onset corpus; unresolved MXF event                         |
| video.decode_integrity    | Corrupted generated packet     | Clean clips; DTS regression                  | Other recoverable codec failures                                 |
| video.frame_rate          | 25 fps versus explicit 30 fps  | Clean CFR/VFR unit cases                     | Rational rates and timebases                                     |
| video.timestamp_integrity | Encoded PTS gap                | Clean clips; missing/VFR unit cases          | Encoded offset/B-frame variants                                  |
| video.black_frame         | Inserted black                 | Ordinary camera controls; edge unit cases    | Leaders and range conversion                                     |
| video.near_black_frame    | Inserted near-black            | Ordinary camera controls                     | Dark scene and boundary variants                                 |
| video.freeze              | Held moving frame              | Static, cuts, fade, zoom/focus/exposure      | Motion settling and edge events                                  |
| video.duplicate_frame     | Copied moving frames           | Ordinary controls; **zoom-settle gap open**  | Continuous low-motion versus unintended repeats                  |
| video.frame_cadence       | Copied moving frames           | Ordinary controls; **zoom-settle gap open**  | Actual cadence-pattern evidence                                  |
| video.luminance_anomaly   | Temporary luma disturbance     | Cuts/fades/exposure adaptation               | Fast legitimate lighting changes                                 |
| video.flash               | Injected short flash           | Cuts and permanent adaptation                | Intentional flashes/strobes                                      |
| video.exposure_anomaly    | Sustained extreme pixels       | Normal exposure adaptation                   | Graphics/snow/slates                                             |
| video.color_anomaly       | Severe solid channel anomaly   | Ordinary camera controls                     | Intentional lighting and graphics                                |
| video.visual_anomaly      | Checkerboard corruption        | Cuts/zoom/focus/exposure                     | Other digital artifacts and fine textures                        |

Dedicated dead/stuck-pixel detection is not implemented or newly claimed. The
320x180 measurement path cannot establish pixel-level coverage of a 4K source.

## Investigations remain visible

The targeted follow-up is recorded in
[duplicate/cadence investigation](PHASE_12_REPEAT_INVESTIGATION.md). It adds a
12-case direct correctness gate, including lossy copies, periodic cadence breaks,
low motion, static inserts and boundaries. Ten cases pass; zoom settling and a
short static insert still fail. No production correction has been accepted.

`investigation.json` is an executable **known-good** zoom-settling case. It renders
each frame independently, including a brief continuous reduction in zoom speed.
The two relevant frames differ; none is copied as a defect injection. Current
duplicate/cadence rules nevertheless emit findings. The CLI reports FAIL and exits

1. The diagnostic pytest verifies this known failure is exposed; it does not
   declare that detector acceptable. After a justified fix, promote this case to the
   ordinary negative corpus and replace the diagnosis test with a passing negative
   assertion. Do not modify its ground truth to match the implementation.

Both detectors currently share `repeats()`; motion before/after plus high RGB
similarity does not establish unintended repetition or a cadence mismatch. Future
changes must preserve copied-frame/freeze/corruption positives and near-duplicate
codec variants, with no filename/timestamp exceptions or global suppression.

Discontinuity uses a 20 ms median-derivative baseline. A smoothly enveloped
percussive negative now complements the original impulse positive. This modest
pair does not establish general transient discrimination. Add attack spectra,
splices/DC steps and window-offset sweeps before changing the algorithm. The MXF
event at 7.567 s remains unresolved, never positive or negative ground truth.

## Local reference intent and review

The ignored `.cache/phase12/reference-review.local.json` pins the four original
paths, saved run IDs, fast fingerprints, exact profile and per-finding review.
It records owner-supplied assignments with explicit indexing:

- WAV channel labels 1/2 = L/R production mix (engine indices 0/1); labels 3–7
  are lavalier ISOs. The seven-channel aggregate is not program loudness.
- MP3 derives from that WAV. The exact conversion/downmix routing is not known.
- MXF absolute audio stream indices 1/2 = L/R production mix; 3–8 are reserved
  ISO sources and intentionally empty. Their silence is not a technical defect.
- MP4 zoom around 2 s and auto-exposure around 4.5 s are known-good behavior.
  The corresponding duplicate/cadence findings are owner-confirmed false positives.
- MXF discontinuity around 7.567 s is unresolved.

These annotations do not remix/reassign source media or silently change runtime
applicability. The three saved multitrack loudness findings remain scope-unresolved
for program compliance even though channel roles are now known. Measuring the
designated L/R program is separate future work. Peak policy violations remain
distinct from confirmed audible damage. Expected unused-track silence must not
be relabeled a defect merely because a generic silence policy emits a finding.

`reference_review.py` opens SQLite with `mode=ro` and `query_only`, pins a read
transaction, verifies source identity and profile, and retains saved dispositions.
Every saved finding is reviewed; unreviewed findings remain unresolved. It reports
REVIEWED, FAIL, or UNRESOLVED rather than inventing a new media verdict. CLI exit
codes are 0 (reviewed), 1 (negative failure), 2 (unresolved only). Reports retain
measurements and execution states, including insufficient quiet evidence.

`--replay-negatives` additionally runs current detectors against original local
sources, preserving their full timelines and using fresh ignored caches. It
asserts only the reviewed negative intervals, and reports all observed findings.
Historical classifications cannot suppress fresh output. The CLI exit code then
reflects the fresh negative replay, separately from the saved-run review. Unknown
audio transients are not implicitly included. This opt-in path needs the originals;
CI never requires them. Missing/changed references fail explicitly, not as a pass.

The windows 1.5–3.2 s (zoom) and 4.0–5.2 s (exposure) are documented review scopes
around approximate operator times, not newly measured edit boundaries.

## Reproduction and validation

From the repository root, with the existing development environment:

```powershell
.venv/Scripts/python.exe -m pytest engine/tests/test_acceptance.py engine/tests/test_audio.py engine/tests/test_video.py -k 'acceptance or golden_manifest or test_manifest' -q
.venv/Scripts/python.exe tools/detector_acceptance.py tests/fixtures/manifests/audio.json --output .cache/phase12/audio-report.json
.venv/Scripts/python.exe tools/detector_acceptance.py tests/fixtures/manifests/video.json --output .cache/phase12/video-report.json
.venv/Scripts/python.exe tools/detector_acceptance.py tests/fixtures/manifests/investigation.json --output .cache/phase12/investigation-report.json
.venv/Scripts/python.exe tools/reference_review.py .cache/phase12/reference-review.local.json --output .cache/phase12/reference-report.json
.venv/Scripts/python.exe tools/reference_review.py .cache/phase12/reference-review.local.json --replay-negatives --output .cache/phase12/reference-replay.json
```

The investigation and saved-reference commands intentionally return nonzero while
the documented acceptance gaps remain. Reports record exact profile/overrides,
source hashes, detector versions and raw observations. Fresh observations embed
bundled FFmpeg provenance, Python version, dependency-lock hash and detector/
generator/harness source hashes. Compare these when evaluating changes across
machines/builds. This records bundled provenance, not an independent binary audit.

### Recorded focused validation

- Initial expanded manifests: 37 passed.
- Expanded corpus/oracle plus shared PCM, vectorized windows, storage/budget and
  rawvideo DTS regression selection: 70 passed, 99 deselected.
- Fresh original MP4 replay: all 10 selected visual event detectors completed;
  only duplicate/cadence findings at 2.565944 s failed the zoom negative scope.
  No findings overlap the reviewed auto-exposure scope. Source full hash, size
  and mtime matched; temporary replay caches were removed.
- Saved reference audit preserves all 11 findings and original verdicts. MP3 is
  REVIEWED, MP4 FAIL, WAV/MXF UNRESOLVED for the documented scope/transient reasons.
- Changed Python files pass Ruff lint/format and strict mypy.
- Final standalone corpus reports: 19 audio + 19 video cases PASS, including
  injected repeat/freeze/corruption positives. The separate zoom-settle
  investigation reports FAIL as required by its unchanged negative expectation.
- Final oracle tests: 26 passed. Repository/specification checks: 3 passed.
  Changed Markdown/JSON pass Prettier; `git diff --check` passes.

Full repository gate, application builds and packaging were not run. The open
zoom-settling failure means detector calibration is not complete. These passing
tests establish the framework and retained positives, not resolution of that gap.

Do not interpret passing synthetic checks as a 30-minute false-positive budget
claim. Use unique reviewed content, separate profile findings from defect false
positives, keep ambiguous events visible and reserve independent holdout material.
Retain the Phase 10 performance tests and cache/thread/resource safeguards. No
production detector change is part of this framework-first increment.

## Subsequent audio follow-up

See [the 2026-10-04 follow-up](PHASE_12_AUDIO_FOLLOWUP.md) for the separately
authorized silence 1.0.1 rounding fix, expanded audio acceptance evidence and
remaining applicability/discontinuity gaps. Earlier results above describe their
original checkpoint and are not rewritten.

The next targeted step defines the [audio applicability contract](PHASE_12_AUDIO_APPLICABILITY_CONTRACT.md)
and records the [discontinuity recall boundary](PHASE_12_AUDIO_BOUNDARY.md).
The contract prototype is developer-only; the tested isolation rule was rejected
because it misses injected clustered and multi-sample clicks.

## Runtime integration checkpoint

The [runtime audio increment](PHASE_12_AUDIO_RUNTIME.md) supersedes earlier
developer-only implementation-status statements. Explicit single-file assignments
now activate runtime channel silence and program loudness applicability; historical
results and unassigned-run behavior are preserved. See that report for remaining
discontinuity failures, validation and UI/batch limitations.

## Acceptance and integration review

The [current review](PHASE_12_ACCEPTANCE_REVIEW.md) closes a saved-report assignment
context gap, strengthens retry/unknown/program-routing coverage, and records the
remaining audio and video limits without changing detector behavior. Its focused
results supersede the previous validation counts, not the earlier evidence.

## Approved V1 release disposition

The [implemented V1 disposition](PHASE_12_V1_ACCEPTANCE.md) preserves all original
ground-truth failures while adding narrowly bound, explicitly approved release
limitations and unresolved-reference reporting. It supersedes earlier statements
that those twelve mismatches necessarily block V1. No detector behavior changed.

## Final automated validation

The [final validation report](PHASE_12_FINAL_VALIDATION.md) records all 22 gate
requirements satisfied, 676 test cases, Windows build/packaging and relocated
smoke results. Automated Phase 12 acceptance is complete and ready for commit
review; clean-machine/public-release acceptance remains separately qualified.
