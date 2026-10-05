# Phase 12 audio follow-up - 2026-10-04

This increment continues the accepted investigation in
[PHASE_12_AUDIO_CALIBRATION.md](PHASE_12_AUDIO_CALIBRATION.md). It does not repeat
reference measurements or the completed duplicate/cadence investigation.

## Established correction: zero tail exemption

The silence detector compared event end with declared duration even when
`ignore_tail_seconds` was zero. A sample-accurate endpoint of 2.0833541667 s
exceeds six-decimal metadata 2.083354 s and incorrectly exempted the entire
silence event. Asset-duration fallback had the same failure.

Before the fix, the focused rounding/edge selection produced 3 failures and
11 passes. `LevelDetector` now applies tail exclusion only when the configured
tail exemption is positive. Only `audio.silence` advances from 1.0.0 to 1.0.1.
There is no threshold relaxation, endpoint clamping, tolerance expansion or
role-based suppression. Positive tail/head exemptions and their strict boundary
comparisons are preserved. Sample-accurate timing and measurement metrics remain
available. General Technical QC 1.2.0, severity and persisted results are unchanged.

New boundary cases cover rounded-down/up metadata, asset fallback, unknown
duration, zero and positive tail settings, the exact positive-tail boundary and
one sample beyond it, head boundary, minimum duration and one sample below it,
and an active-audio clean control. The existing real decoder silence regressions
also pass. The fix adds no buffers or decoding passes; shared PCM, cancellation,
resource limits and bounded-memory processing are untouched.

## Discontinuity: strengthen the gate, reject an incomplete correction

Existing evidence established two independent problems: a fixed 20 ms context
flags legitimate sharp analytic attacks (including window-phase sensitivity),
and the median of the maximum derivative across channels can mask an injected
click when an unrelated channel is busy. Production logic remains unchanged.

Three deterministic manifest cases were added with generator version 1.3.0:

- `masked_swapped`: channel permutation of the masked injected click, requiring
  detection at 2 s within one sample. It remains a missed positive.
- `sharp_busy`: a continuous analytic sharp transient paired with unrelated
  high-frequency activity, requiring no finding. Current production passes.
- `clean_busy`: two continuous tones with no injected edit, requiring no finding.
  Current production passes.

Two diagnostic regressions evaluate the proposed per-channel baseline using the
unchanged profile-derived jump and ratio limits. That change recovers the masked
click, but also unmasks the legitimate sharp transient. Thus per-channel
normalization alone cannot satisfy the positive and negative labels. It is not
promoted to production. Simultaneity, channel order and a busy neighbour provide
no sound basis for declaring a fault or exempting it. Threshold tuning and
reference-specific clearing were rejected as before.

The expanded discontinuity corpus is **11 PASS / 7 FAIL**: five legitimate-content
false positives and two masked-click false negatives. The failures remain real
acceptance failures, not xfails, skips or rewritten expected outputs. Other
injected impulses, DC step, phase splice and independent mono-stream positives
remain detected. No claim of complete discontinuity recall is made.

Before a safe production correction, a candidate must pass both baseline pairs,
all sharp/sustained/window-boundary negatives, and the existing injected sample,
step, splice and simultaneous/delayed positives. Further evidence should include
reviewed independent sharp production sounds and labelled injected faults over
multiple onset phases, sample rates, channel arrangements and recording noise
levels. A sustained DC or waveform-continuity feature must demonstrate those
results rather than being inferred from the unresolved MXF event. The available
corpus does not yet establish a safe discriminator.

## Explicit program and channel applicability

The new MXF acceptance case checks exactly six raw silence WARNs on streams 3-8,
with both active production legs remaining free of silence findings. Its intent
is deliberately unused ISO audio; those WARNs are preserved profile/measurement
evidence, not confirmed technical defects. The existing byte-identical unused
ISO/required-silent pair remains in the gate, preventing automatic role inference
from silence. This is not an applicability-aware verdict implementation.

A new cross-stream program test explicitly joins MXF streams 1/2 as L/R and
compares integrated loudness with the equivalent stereo WAV. It passes within
0.002 LU; source hashes remain identical and owned processes are cleaned up.
Together with the existing seven-channel WAV L/R selection test, this verifies
developer measurement scope without changing runtime routing or verdicts.

The smallest explicit solution remains a per-run, persisted assignment snapshot:
ordered `(stream_index, channel_index)` members for each program, separate
required/optional/unused/unknown channel roles, and assignment provenance.
Validate members against probed streams and reject invalid or duplicate members
within a program; never infer unused status from silence. Program loudness must
name its selected program. Raw channel measurements remain attached even when an
explicit applicability rule excludes a known-unused track from defect judgement.
Unknown roles must remain unresolved; required silent channels must stay visible.
A role labelled optional is not itself an instruction to suppress silence.

This requires an explicit applicability contract/policy decision and is proposed,
not silently implemented in General Technical QC 1.2.0 or its severity semantics.
Legacy aggregate and mono-leg measurements must never be relabelled as program
measurements. New routing requires a new measurement with its scope retained.

## Effect on accepted references

Original media and the saved project database were not opened or modified in this
step. Existing local assignments and measurements are retained; the local review
manifest now records this follow-up and supersedes the earlier unfixed-EOF note.

- WAV L/R -25.568 LUFS and MP3 stereo -27.026 LUFS remain below the current
  program band. WAV aggregate multitrack loudness is not interchangeable with
  designated L/R loudness; conversion routing/gain remains unknown for MP3.
- MXF L/R -23.663 LUFS is within the current program band. Saved mono-leg
  measurements are not equivalent and their historical findings remain intact.
- MXF sample/true-peak exceedances remain valid current-profile measurements;
  these alone do not establish audible distortion.
- The MXF transient near 7.567 s remains unresolved. No fresh classification or
  discontinuity detector change was made.
- Given the already measured all-zero PCM and rounded duration, future silence
  runs are expected to expose raw WARNs on MXF streams 3-8. Synthetic MXF stream
  scope and rounding regressions verify the relevant mechanisms; a fresh original
  replay was deliberately not repeated. Their reviewed intent remains expected
  silence. This correction does not fix applicability-aware verdicts.
- WAV/MP3 may similarly gain previously omitted qualifying EOF-silence findings
  if present; no claim of a fresh whole-reference clean run is made.

Duplicate/cadence ambiguity and documented counterexamples are unchanged. No
additional image heuristics or temporal-expectations architecture were attempted.

## Focused validation

Commands run for this increment:

```powershell
.venv/Scripts/python.exe -m pytest engine/tests/test_audio_calibration.py -k 'silence_edge_contract or duration_rounding' -q
.venv/Scripts/python.exe -m pytest engine/tests/test_audio_calibration.py -k 'silence_edge_contract or duration_rounding or per_channel_baseline or only_silence' -q
.venv/Scripts/python.exe -m pytest engine/tests/test_audio_calibration.py engine/tests/test_audio.py engine/tests/test_acceptance.py -k 'calibration or silence or discontinuity_isolated or current_profile_document' -q --tb=short
.venv/Scripts/python.exe -m ruff check engine/src/mediaqc_engine/detectors/audio/levels.py engine/tests/test_audio_calibration.py engine/tests/test_audio.py tools/generate_test_media/audio.py
.venv/Scripts/python.exe -m mypy engine/src/mediaqc_engine/detectors/audio/levels.py engine/tests/test_audio_calibration.py tools/generate_test_media/audio.py
```

- Before correction: 3 failed / 11 passed (rounding and edge selection).
- After correction: 17 passed (rounding, edges, baseline diagnostics and versions).
- Expanded focused gate: **42 passed / 7 failed / 105 deselected**. All seven
  failures are the documented discontinuity acceptance gaps. Silence regression,
  applicability (3 cases), explicit L/R routing, isolated-click positive and
  unchanged-profile hash checks pass.
- An initial sandbox test run encountered pytest-cache permissions; the same
  focused command completed with approved access. No tests were skipped to hide
  this failure. The expanded gate intentionally exits nonzero for detector gaps.

Final focused static checks also pass: Ruff lint and format for the four touched
Python files, strict mypy for the three implementation/calibration files,
Prettier for the touched documentation/manifests, and `git diff --check`.
`node --test tests/repository.test.mjs` passes all three small repository checks,
including specification manifest byte counts. These are not the full quality gate.

Phase 12 is **not ready for final validation**. Recommended next step: review the
explicit program/channel applicability contract before implementing it, then
continue discontinuity discrimination with the paired acceptance gate and
independent reviewed content. Full quality gate, build, packaging, installer,
portable generation, commit, push, merge and PR remain unperformed.
