# Phase 12 — audio calibration and applicability, 2026-09-27

**Not ready for final validation.** Production detectors, General Technical QC
1.2.0, severity semantics and historical results are unchanged. The new corpus
exposes discontinuity specificity/recall gaps and an independent silence boundary
bug. No threshold was adjusted to clear a reference.

## Discontinuity model and reference evidence

The current rule takes the maximum absolute adjacent-sample difference across a
stream's channels, then its median within fixed, non-overlapping 20 ms windows.
With the unchanged sensitivity of 0.7, candidates require both a normalized jump
of at least **0.26** and a derivative/median ratio of at least **19.5**. Candidate
samples within 20 ms are merged. The reported confidence is a bounded function
of that ratio, not a calibrated probability that a technical fault occurred.

This establishes a locally unusual waveform change, not its cause. It does not
measure attack/decay continuity, a splice model, spectral evolution or agreement
across independent mono streams. Taking the channel maximum before estimating
the baseline also allows unrelated activity to hide another channel's click.

`tools/audio_reference_probe.py` reads the original MXF without producing a media
copy. The 7.50–7.68 s excerpt uses exact sample coordinates at 48 kHz, preserving
the production window alignment. The first context block is excluded because
its preceding sample is absent. The following measurements reproduce the saved
ratios and candidate times:

| Absolute MXF stream | Candidate interval, seconds | Largest jump | Median derivative | Ratio     | Qualifying samples |
| ------------------- | --------------------------- | ------------ | ----------------- | --------- | ------------------ |
| 1 / Left            | 7.565792–7.566750           | 0.510367     | 0.023945          | 21.313747 | 2                  |
| 2 / Right           | 7.566854–7.569104           | 1.315192     | 0.015605          | 84.279017 | 15                 |

Both fall inside a larger attack/decay event. In the 7.56–7.58 s window, RMS is
0.16065/0.13752 (L/R), compared with 0.00302/0.01470 in the preceding window;
energy remains elevated afterward. Mean levels do not exhibit an obvious lasting
DC step in this short excerpt. Hann-window spectral energy above 8 kHz is about
3.1%/19.2% during the event. These are descriptive measurements, not new gates.

First qualifying samples differ by 51 samples (1.0625 ms), which is a threshold
crossing difference, not a measured acoustic propagation delay. Zero-lag waveform
correlation over the event window is 0.074; searching ±2 ms gives a largest
absolute correlation of 0.253 (signed -0.253, lag -55 samples). This does not
establish a shared waveform or independent faults. A real sound can reach
different microphones with different filtering/delay; shared digital faults can
also affect multiple channels. Neither simultaneity nor low correlation adjudicates
intent. The MXF transient remains **UNRESOLVED**, neither a positive nor a clean
acceptance case.

Useful future evidence includes per-channel jump polarity/duration, interpolation
or splice residuals, pre/post spectral and envelope continuity, DC persistence,
and cross-channel lag/coherence. Each needs paired legitimate-transient and fault
tests. A filtered click can ring; a legitimate attack can be broadband. None of
these features independently proves a fault, and no speculative combination was
promoted into production.

## Added deterministic acceptance coverage

`audio_discontinuity.json` contains 15 cases using unchanged thresholds. Timing
tolerance is one 48 kHz sample for injected faults; severity and stream indexes
must match, with no unexpected findings allowed.

| Coverage                                                                   | Current result                                    |
| -------------------------------------------------------------------------- | ------------------------------------------------- |
| Impulses one sample before/after a 20 ms boundary                          | PASS, both edges retained/merged                  |
| Injected DC step and hard phase splice                                     | PASS                                              |
| Simultaneous and 1 ms separated stereo clicks                              | PASS; shared activity is not exempted             |
| Click in one channel beside continuous high-frequency activity in another  | **FAIL: missed click**                            |
| Continuous analytic sharp burst, mono/stereo/1 ms delayed stereo           | **FAIL: three false-positive cases**              |
| Longer continuous burst aligned to the block boundary                      | PASS                                              |
| Same longer burst moved 15 ms                                              | **FAIL: false positive**                          |
| Continuous high-frequency tone                                             | PASS                                              |
| MXF with simultaneous clicks in mono streams 1/2 and six empty ISO streams | PASS, one correctly timed event per active stream |
| Same MXF layout with legitimate sharp bursts                               | **FAIL: false positives on both active streams**  |

The sharp negative has a continuous 100 µs analytic attack and an 8 kHz carrier;
there is no sample replacement, hard splice or clipping. The waveform and its
first derivative are continuous at onset. Its brief energy is nevertheless a
derivative outlier. Moving a sustained onset across a fixed window changes the
median baseline enough to change the result. The masked-click case establishes
a separate multichannel recall problem. All failures remain direct assertions;
none is skipped, xfailed or relabelled to fit the detector.

The next detector step should investigate a per-channel, phase-robust context
model against these same positives and negatives, preserving vectorized bounded
windows and event timing. Fixing channel masking alone would not resolve sharp
transient specificity. This increment does not claim a safe complete correction.

## Program loudness: scope changes the interpretation

The supplied channel assignments are retained in the local review manifest.
Additional developer-only measurements explicitly select WAV channels 1/2 or
join MXF absolute mono streams 1/2 as L/R. MXF stream start times and channel
counts are checked; there is no inferred downmix. Processing is read-only and
uses the existing bundled R128 implementation. A synthetic routing regression
checks that the five extra ISO channels do not contribute to the selected L/R
measurement. This is not an independent certification of the R128 implementation.

| Source / scope                    | Integrated LUFS | Interpretation against -23 ±1 LU                                                                                                           |
| --------------------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| WAV saved seven-channel statistic | -24.123         | Numerically outside the bound, but not the designated L/R program. Undeclared multitrack layout must not be treated as a surround program. |
| WAV explicitly selected L/R       | **-25.568**     | Program is 1.568 LU below the lower bound; profile compliance, not proof of damage.                                                        |
| MP3 saved stereo output           | -27.026         | 3.026 LU below the lower bound for that delivered stereo output. Exact conversion/downmix/gain routing remains unknown.                    |
| MXF saved Left alone              | -29.034         | A mono-leg statistic; do not interpret as stereo-program loudness.                                                                         |
| MXF saved Right alone             | -24.622         | Same scope limitation.                                                                                                                     |
| MXF explicitly joined L/R         | **-23.663**     | Within the current program band. This does not change the saved FAIL verdict or other peak findings.                                       |

The MP3 is confirmed to derive from the WAV, but the different loudness values
do not establish a conversion defect. Do not assume that the MP3 is exactly the
WAV L/R selection. The old aggregate/mono measurements remain evidence with
their original applicability limitations, rather than being overwritten by the
new program measurements.

## Sample peak, true peak and clipping

The saved MXF Right sample peak is **-0.010609 dBFS**, exceeding the current
-0.1 dBFS limit by 0.089391 dB. True peak is **+0.796211 dBTP**, exceeding the
-1.0 dBTP limit by 1.796211 dB. The explicit L/R measurement retains the same
1.096 linear true-peak estimate. The earlier excerpt verification and focused
sample/true-peak regressions support the measurements; no new independent
oversampling accuracy certification is claimed.

These are valid current-profile compliance findings, not independently confirmed
audible distortion. The saved clipping detector did not report qualifying
clipping runs. Sample maxima, reconstructed intersample maxima and clipping-run
evidence are different measurements and all remain available. Intentionally
produced transients do not automatically exempt selected peak policy limits.

## Empty ISO tracks and the missing applicability contract

MXF streams 3–8 are owner-declared unused/empty ISOs. Their silence is expected
and is not a technical defect. Retained metrics show digital silence (the -300
dB numerical floor) and `NO_GATED_AUDIO` rather than measured program loudness.

The current profile/engine has no general required/optional/unused role or
cross-stream program assignment. It cannot infer those roles from low level.
`audio_applicability.json` therefore pairs identical silence media with two
explicit review intents: unused ISO and unexpectedly silent required channel.
Both retain the raw six-second silence measurement and unchanged profile WARN;
only the first is known not to be a technical defect. These are measurement and
policy-preservation tests, **not** proof of implemented applicability-aware
verdicts. No broad all-silent-channel exemption was added.

An additional bug explains the absence of saved MXF silence findings: decoded
duration is 39.205833333… s while declared duration is 39.205833 s. `silence`
compares the event end against declared duration even when `ignore_tail_seconds`
is zero, accidentally exempting the EOF event. A required-channel regression
reproduces the same problem with six-decimal duration rounding; exact duration
passes. This omission is not evidence of intent awareness and must not become
the mechanism for handling unused ISOs. The bug is exposed, not silently fixed
alongside an unresolved applicability policy.

The smallest explicit solution to propose is an immutable per-run audio mapping:
program IDs with ordered `(stream_index, channel_index)` members and explicit
channel roles such as required, optional, unused or unknown, including assignment
provenance. Program-level measurements use the selected mapping; raw per-channel
measurements remain retained. Applicability of silence to verdicts must be an
explicit rule, with unexpectedly silent required channels still reported. No
such schema, UI, routing default, migration, suppression or profile change is
implemented here. The EOF rounding bug should receive its own narrow fix/test
alongside that review, without pretending it resolves applicability.

## Validation and artifacts

```powershell
.venv/Scripts/python.exe tools/detector_acceptance.py tests/fixtures/manifests/audio_discontinuity.json --output .cache/phase12/audio-discontinuity-final-report.json
.venv/Scripts/python.exe tools/detector_acceptance.py tests/fixtures/manifests/audio_applicability.json --output .cache/phase12/audio-applicability-report.json
.venv/Scripts/python.exe -m pytest engine/tests/test_audio_calibration.py engine/tests/test_audio.py engine/tests/test_acceptance.py -k 'calibration or discontinuity_isolated or current_profile_document' -q
.venv/Scripts/python.exe -m pytest engine/tests/test_audio_calibration.py engine/tests/test_audio.py -k 'explicit_lr_program or true_peak or reference_probe_requires' -q
.venv/Scripts/python.exe tools/audio_reference_probe.py .cache/phase12/reference-review.local.json --output .cache/phase12/audio-reference-probe.json
```

- Discontinuity manifest: **9 PASS, 6 FAIL** (five false-positive cases and one
  missed positive); CLI exit 1 preserves the gate.
- Applicability measurement/policy manifest: **2 PASS**.
- Initial calibration regression selection: **19 passed, 7 failed, 107 deselected**;
  six discontinuity gates plus the silence-rounding regression failed. The L/R
  routing test was added afterward.
- Additional focused program routing, sample/true-peak and probe-bound checks:
  **11 passed, 97 deselected**.
- Changed Python passes Ruff lint/format and strict mypy. Markdown/JSON formatting
  and diff-whitespace checks pass.

The local manifest now links supplementary L/R evidence and explicitly retains
the MXF transient as unresolved. Source fingerprints plus before/after full hash,
size and mtime checks guard the new reference measurements. Reports retain
measurements rather than replacing saved findings.

The read-only saved-run audit confirms all 11 pinned findings and their saved
verdicts are identical to the earlier report. The whole database file hash differs
from that older report, but was stable before/after this audit; the cause of the
intervening physical-file difference was not investigated. No historical result
change is inferred from that file-level difference.

The diagnostic excerpt is capped at 180 ms per mono stream; its metric helper
rejects inputs above 500 ms. Whole-program loudness is streamed with bounded
metadata parsing, no whole-file PCM buffer, and owned-child cleanup. Production
PCM sharing, cancellation, performance and memory safeguards are untouched.

The accepted duplicate/cadence ambiguity and its counterexamples remain as
documented in `PHASE_12_TEMPORAL_CONTEXT.md`; no further image heuristics or
temporal-expectation architecture were attempted. Another targeted audio step
is needed before final validation. No full quality gate, release build, package,
installer, portable artifact, commit, push, merge or PR was performed.

## Subsequent audio follow-up

See [the 2026-10-04 follow-up](PHASE_12_AUDIO_FOLLOWUP.md) for the separately
authorized silence 1.0.1 rounding fix, expanded audio acceptance evidence and
remaining applicability/discontinuity gaps. Earlier results above describe their
original checkpoint and are not rewritten.
