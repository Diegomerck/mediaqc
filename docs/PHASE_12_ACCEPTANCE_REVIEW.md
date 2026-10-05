# Phase 12 acceptance and applicability integration review

This continues the [runtime checkpoint](PHASE_12_AUDIO_RUNTIME.md). Existing
uncommitted work is retained. No original reference media or historical reference
project was opened. No detector threshold, detector algorithm/version, profile,
severity rule or historical verdict was changed in this pass. Silence 1.1.0 still
includes the accepted 1.0.1 zero-tail correction.

## Production correction: complete saved report context

Review found that offline reports carried general applicability notes and finding
scopes but omitted the assignment snapshot. A PASS run with no findings could
therefore omit the exact channel expectations, program mapping and source binding.
Two new reopen/report regression cases failed with the missing report section
before the correction.

Report generator 1.1.0 now includes `Saved audio applicability` for assigned runs:
source SHA-256, assignment identity, provenance, saved policy version, original
contract document, normalized relational channel roles/expectations (including
omitted channels as unknown), and ordered program members. It reads only saved DB
state under the existing report transaction and text bound. HTML/PDF export and
existing artifacts/history remain independent of the current source. Unassigned
runs do not acquire fabricated assignments or changed verdicts. Previously
exported files are not rewritten.

Files changed in production this pass: `db/audio_assignments.py` and `reports.py`.
This is report context, not signal-processing or applicability-policy revision.

## Applicability review and focused coverage

- Expected activity is independent of role. Explicit required silence retains the
  profile severity; explicit unused silence remains INFO; omitted/unknown activity
  remains INFO/UNRESOLVED. No role or observed quietness invents intent.
- A new test compares the same six-second silent fixture with no assignment
  (legacy WARN) and an explicit empty assignment (INFO, unknown coverage). The
  latter PASS is explicitly qualified as unresolved, not technical cleanliness.
- Existing seven-channel tests retain a required silent ISO under active L/R,
  exact per-channel previews/timing, and expected-unused/unknown evidence. MXF
  role-switch tests retain six unused INFO events and detect one explicitly
  required silent ISO when that expectation changes.
- A new real-decoder test simultaneously measures the L/R program and an explicitly
  designated mono ISO program using channel 3. The measured difference matches
  their known 10:1 amplitude ratio and mono/stereo energy weighting, demonstrating
  routing beyond the default first two channels. Raw stream metrics remain saved.
- A new source/retry test creates an 18-second synthetic WAV larger than the fast
  fingerprint coverage, completes a run, closes the project, alters one middle
  byte while restoring size/mtime, and reopens/retries. The fast fingerprint is
  unchanged but full SHA-256 differs. Retry fails MEDIA_CHANGED before detector
  execution; the old run, assignment, measurements and verdict remain unchanged.
  This deliberate mutation is confined to a disposable generated test fixture.
- Reopened reports with and without declared channels/programs retain all saved
  intent and source identity in HTML and PDF. Existing legacy report, migration,
  program clock, immutable snapshot, evidence and runtime tests remain passing.

The implementation remains intentionally limited to explicit single-file stdio
assignments. No desktop assignment editor, batch propagation, implicit alignment,
resampling or program waveform preview is added. Unsupported program clocks fail
explicitly before measurement; partial per-program recovery is not implemented.
Sample peak, true peak and other detectors remain physical-stream scoped.

Source-bound execution/retry uses full SHA-256. Interactive `evidence.read` still
uses the established bounded fast fingerprint plus artifact checksum; it is not a
fresh full-file identity proof on every preview. Offline reports verify saved
artifacts against saved results, not against today's media. Adding full-file reads
to synchronous preview requests would need a separate cancellation/responsiveness
design; this pass does not silently add that cost or claim it already exists.

## Discontinuity: no safe production discriminator established

The seven failures still arise from two established mechanisms:

1. The 20 ms shared maximum-derivative baseline is raised by an unrelated active
   channel and masks the injected click, including after channel order reversal.
2. Legitimate sharp attacks exceed the same amplitude/derivative gates. Their
   apparent isolation depends on attack duration and position within the window.
   Simultaneity or a small inter-channel delay does not establish their cause.

Existing complete paired-corpus experiments remain regression evidence:
channel-local baseline alone also exposes the legitimate `sharp_busy` transient;
the candidate-count veto loses clustered/wide clicks; two-sided interpolation
loses moderate steps/plateaus, shortens wide-click extent and still flags
`sustained_shifted`. None is promoted and none of their positive/negative labels
is weakened.

This pass adds one genuinely different diagnostic: an explicit causal ambiguity
construction, rather than another feature cutoff. For each of the five sharp
negative constructions, independently convolve a one-sample injected fault with a
fixed causal FIR response derived from the corpus's analytic attack/decay equation,
then add the clean background. The resulting 40 ms, 16-bit observations are
byte-identical to the legitimate authored sound, including stereo and delayed
cases. For `mxf_sharp`, this checks its underlying PCM construction; it does not
repeat container or original-reference decoding. The tests also establish that
adding the busy unrelated channel does not change either the click-channel or
sharp-attack-channel samples.

This rejects the proposition that ringing, polarity, derivative shape or smooth
recovery alone proves a legitimate source. A fault upstream of filtering can ring;
coherence can occur for shared faults and legitimate signals. The fixed response
is an existence counterexample, not a fitted model of the MXF reference or a claim
that all five legitimate sounds are defects. Only the local 40 ms observation is
asserted identical here, not whole-file audio identity. This does not prove that
no restricted-domain classifier can improve specificity; it does mean this corpus
has not justified a broadly safe causal discriminator. No production rule changed.

The diagnostic tests are deliberately separate from the production acceptance
manifest. Passing counterexample tests does not turn required clean negatives
into allowed findings or discharge the seven acceptance failures. Clustered,
wide, moderate-step, plateau and existing valid detections remain required and
are detected by unchanged production.

## Every remaining acceptance failure

Audio discontinuity: 22 manifest cases, 15 passing and 7 failing:

| Fixture suffix (`audio.discontinuity.*.001`) | Failure                                           |
| -------------------------------------------- | ------------------------------------------------- |
| `masked`                                     | Missed injected click                             |
| `masked_swapped`                             | Missed injected click with channels reversed      |
| `sharp`                                      | False positive on legitimate attack               |
| `sharp_stereo`                               | False positive on simultaneous legitimate attacks |
| `sharp_delayed`                              | False positive on delayed legitimate attacks      |
| `sustained_shifted`                          | False positive on shifted legitimate onset        |
| `mxf_sharp`                                  | False positives on both mono production legs      |

Video evidence was reviewed, not regenerated. The five documented failures remain:
`video.zoom_settle.001`, `video.static_between_cuts.001`,
`video.intentional_hold.001`, `video.intentional_hold_lossy.001`, and
`video.intentional_periodic_hold.001`. The original reviewed MP4 zoom remains a
known duplicate/cadence false positive. The [temporal investigation](PHASE_12_TEMPORAL_CONTEXT.md)
already establishes three entire encoded-file identity pairs with opposite causal
intent. PTS, larger motion context and image-only features cannot distinguish those
pairs. That proof does not assert every zoom is intrinsically ambiguous, but no
new evidence supports a safe correction for the remaining zoom/static cases.
No video detector or optional temporal-expectations architecture changed.

Original WAV/MP3/MXF results were not rerun or reinterpreted. The accepted L/R
measurements remain -25.568, -27.026 and -23.663 LUFS respectively; unrelated ISO
or mono-leg measurements are not substitutes. The MXF peak limit exceedances do
not establish audible distortion, streams 3-8 are intentionally empty under this
reference's explicit intent, and the approximately 7.567 s transient is unresolved.

## Focused validation

```powershell
.venv/Scripts/python.exe -m pytest engine/tests/test_audio_runtime.py engine/tests/test_audio_program_clock.py engine/tests/test_audio_applicability_contract.py engine/tests/test_discontinuity_shape_probe.py engine/tests/test_discontinuity_identifiability.py engine/tests/test_reports.py -q --tb=short
.venv/Scripts/python.exe -m pytest engine/tests/test_audio_calibration.py engine/tests/test_audio.py engine/tests/test_acceptance.py -k 'calibration or silence or discontinuity_isolated or current_profile_document or shared_pcm or loudness_numeric or windowed_loudness or silent_integrated' -q --tb=short
```

- Runtime, clock, contract, rejected-rule, new ambiguity and report tests:
  **113 passed**. Six new runtime/report cases and six new diagnostic cases are
  included; the prior regression evidence remains present.
- Focused production audio gate: **64 passed / 7 failed / 100 deselected**.
  All seven failures are listed above; no new failure appears. This selection
  includes the assigned/unassigned timing and shared-PCM checks added previously,
  explaining the pass-count increase over the earlier 51-pass checkpoint.
- Focused Ruff lint/format and strict mypy pass for the four Python files changed
  this pass. Documentation formatting and all three repository/specification checks pass;
  `git diff --check` passes.

A sandbox pytest attempt encountered Windows cache/temp access denial; the same
focused tests were rerun with the existing approved pytest permission. No original
media or reference DB was accessed. No full gate, build, packaging, commit, push,
merge or PR was performed.

## Readiness and smallest next step

The runtime/report increment has a defensible stopping point. Phase 12 is **not
ready to claim final acceptance** while these 12 synthetic failures remain. A full
validation run cannot resolve contradictory source-only intent requirements.

The smallest next step is an explicit review decision about acceptance of
observationally ambiguous candidates: retain measured evidence and acknowledge
unresolved intent, or supply additional trusted provenance/expectations. This is
not authorization to change policy or implement the deferred temporal design.
For discontinuity improvement, obtain an independently reviewed paired holdout
with clean acquisition context and known injected faults (including pre/post
filtering and masked/clustered/multi-sample cases), plus exact timing ground truth.
Test a proposed mechanism against that evidence and all current counterexamples
before promoting it. Do not label the MXF transient to manufacture ground truth,
and do not conduct another cutoff sweep just to clear these seven examples.
