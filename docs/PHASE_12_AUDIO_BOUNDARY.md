# Phase 12 applicability and discontinuity boundary

This step continues the accepted audio checkpoint. The silence 1.0.1 zero-tail
fix is preserved. No production code, threshold, severity or historical result
changed in this increment. Original reference media and the saved project database
were not opened; previous reference analyses were not repeated.

## Applicability result

[The explicit contract](PHASE_12_AUDIO_APPLICABILITY_CONTRACT.md) defines source-bound
immutable program/channel assignments, separates channel role from expected
activity, and separates measurements, scope/compliance evaluation and technical
review. A developer-only parser and tests validate this contract without routing
production audio or changing verdicts. Unknown channels never become unused by
inference; explicitly expected ISO channels remain applicable to silence policy.

A further concrete integration gap is documented: stream-level RMS can conceal
silent required WAV ISO channels beneath an active mix. Existing per-channel RMS
is useful evidence but is not per-channel timed silence detection. Production
integration needs explicit scope, per-channel event evidence and versioned policy,
not simply an unused-channel flag that suppresses a whole stream.

## Discontinuity experiment

The previous step rejected per-channel baselines alone. This step tests an
additional hypothesis: use the existing profile-derived amplitude/derivative ratio
limits per channel, but retain a window only when it contains at most two candidate
samples per channel. A single injected sample generally contributes two edges;
a sustained oscillatory attack contributes many. The value two describes the
experimental single-sample shape, not a changed production profile threshold.

The helper in `tools/discontinuity_shape_probe.py` is bounded to 960 samples
(20 ms at 48 kHz), at most 64 channels, and one previous sample per channel. It
rejects oversized/nonfinite inputs. It is not imported by production detectors.
The trial quantizes the existing synthetic recipes identically to 16-bit fixtures
and uses the existing profile merge gap. For MXF recipe entries, the diagnostic
uses equivalent underlying stereo waveforms; the production acceptance gate still
runs actual generated multi-stream MXF. The trial does not prove container routing.

This hypothesis matches the expected positive/negative labels of the prior 18
manifest cases, including masked clicks and sharp attacks. Two additional causal
positives then disprove safe recall:

- `audio.discontinuity.click_cluster.001`: two injected 0.9-amplitude sample clicks
  1 ms apart. Required event: 2.000000 to 2.001041667 s, one-sample tolerance.
- `audio.discontinuity.wide_click.001`: an injected three-sample triangular pulse
  [0.45, 0.9, 0.45], creating four edges. Required event: 2.000000 to 2.000083333 s,
  one-sample tolerance.

Production detects both. Per-channel candidates without the isolation veto detect
both. The proposed veto suppresses both completely. It is therefore **rejected**.
Passing diagnostic tests assert this counterexample, not acceptance of the missed
faults. The production manifest retains both positive expectations and exact WARN
severity. New recipes have generator version 1.4.0; prior recipes are unchanged.

This establishes a narrower unresolved boundary: few derivative edges can help
separate the current isolated-click controls from ringing attacks, but an edge-count
veto confuses clustered/multi-sample faults with legitimate activity. Increasing a
count cutoff merely to fit these examples would be tuning, not established
correctness. No cutoff sweep, spectral exemption or reference-specific override
was promoted. Further discrimination needs a validated contextual model retaining
multi-sample/burst faults and independent reviewed transient negatives, including
window phase, recording noise and sample-rate variation. This does not prove all
future algorithms impossible; it rejects the tested rule on concrete recall evidence.

## Remaining production acceptance failures

The discontinuity corpus is now 20 cases: **13 PASS / 7 FAIL**. The two new positives
pass without changing production. The existing failures are unchanged:

| Case suffix                              | Failure                                                       |
| ---------------------------------------- | ------------------------------------------------------------- |
| `masked`, `masked_swapped`               | Missed injected click with busy unrelated channel             |
| `sharp`, `sharp_stereo`, `sharp_delayed` | Legitimate sharp transient flagged                            |
| `sustained_shifted`                      | Legitimate attack flagged at shifted window phase             |
| `mxf_sharp`                              | Legitimate transient flagged on both independent mono streams |

These remain ordinary failing acceptance tests, not xfails or tolerated output.
The MXF reference transient near 7.567 s remains unresolved. Known loudness/peak
interpretations and owner-declared unused ISO intent remain as previously reviewed.
The contract does not reinterpret aggregate/mono measurements as L/R programs.
Duplicate/cadence findings, temporal ambiguity and counterexamples are unchanged;
no new image-only investigation was performed.

## Validation and next step

Focused commands:

```powershell
.venv/Scripts/python.exe -m pytest engine/tests/test_audio_applicability_contract.py engine/tests/test_discontinuity_shape_probe.py -q --tb=short
.venv/Scripts/python.exe -m pytest engine/tests/test_audio_calibration.py engine/tests/test_audio.py engine/tests/test_acceptance.py -k 'calibration or silence or discontinuity_isolated or current_profile_document' -q --tb=short
.venv/Scripts/python.exe -m ruff check tools/audio_applicability_contract.py tools/discontinuity_shape_probe.py tools/generate_test_media/audio.py engine/tests/test_audio_applicability_contract.py engine/tests/test_discontinuity_shape_probe.py
.venv/Scripts/python.exe -m mypy tools/audio_applicability_contract.py tools/discontinuity_shape_probe.py tools/generate_test_media/audio.py engine/tests/test_audio_applicability_contract.py engine/tests/test_discontinuity_shape_probe.py
```

Contract, scope characterization and bounded experiment tests: **46 passed**.
Ruff lint and strict mypy pass for all five touched Python implementation/test
files.

The production calibration selection reports **44 passed / 7 failed / 105
deselected**. All failures are the seven discontinuity gaps above. Silence fix,
profile identity and the two new defect positives pass. No full quality gate,
Windows build, packaging, installer, portable generation, commit, push, merge or
PR was performed.

Phase 12 is not ready for final validation. Next, review the defined applicability
contract and explicitly authorize its runtime schema/policy integration before
changing new-run verdict semantics. Discontinuity needs independent reviewed
negative content and richer injected multi-sample faults against any proposed
contextual discriminator. The new recall counterexamples are mandatory gates.
