# Phase 12 runtime audio applicability and interpolation investigation

This increment implements the accepted applicability direction for explicitly
assigned **new single-file runs**. Original reference media and the saved reference
project were not opened or modified. Earlier reference investigations were not
repeated. No reference filename appears in runtime policy.

## Runtime contract and persistence

`analysis.start` now accepts optional `audio_assignment` using the accepted 0.1.0
contract. `system.capabilities` advertises `explicit_audio_v1` and schema 4.
The caller supplies explicit assignments; omission retains legacy behavior. The
engine does not infer roles from layout, number of channels, filename or silence.
Desktop assignment editing and batch assignment propagation are not implemented;
this smallest runtime integration is available through documented stdio IPC.

The contract implementation moved into `qc/audio_applicability.py`; the developer
module re-exports it so there is one validation implementation. Validation binds
ordered program members and channel role/expectation to source SHA-256 and probed
audio topology. Inputs are copied before worker dispatch. The worker verifies full
source SHA-256 before measurement and after analysis/evidence, with cancellation
checks and 1 MiB read buffers. A stale assignment fails before detector execution.

Schema 4 stores an immutable assignment header, channel records, programs and
ordered members relationally, plus the original contract JSON for audit. Updates
are prohibited by database triggers; there is no assignment-edit/delete API.
Retry preserves and revalidates the snapshot; new assignments require new runs.
Migration retains existing history and the established backup/rollback strategy.
No old run is assigned new semantics or recalculated. `analysis.get` exposes the
saved assignment and applicability policy.

The separate versioned policy document `qc/audio_applicability_v1.json` declares
INFO for expected-unused/unknown silence and unassigned program scope. Expected
channel silence and designated-program violations use the unchanged selected QC
profile severity and thresholds. General Technical QC 1.2.0 is unchanged; no new
technical-only profile was introduced. Finding disposition and overall severity
aggregation remain unchanged. This is an explicit new-run applicability policy,
not an undocumented relaxation of the existing profile.

## Per-channel silence and evidence

Silence detector 1.1.0 preserves the accepted 1.0.1 zero-tail correction. For an
assigned run it maintains one bounded silence-region state per channel using the
existing 10 ms PCM windows and profile threshold/minimum duration/head/tail gates.
An active mix can no longer conceal a silent **explicitly expected** ISO channel.
No-assignment runs retain the prior stream-RMS behavior.

Every qualifying channel event retains measured RMS, duration, exact channel scope,
profile thresholds, assignment identity, applicability state and original policy
severity. Expected channels produce the selected profile severity. Explicit unused
channels retain INFO evidence labelled EXPECTED_UNUSED. Unknown/omitted expectations
retain INFO evidence labelled UNRESOLVED, not confirmed defects. Whole-stream peaks,
per-channel RMS and sample counts are retained independently of applicability.

Waveform/spectrogram evidence for channel-scoped silence now selects that exact
channel with a unity-gain pan instead of showing a downmix that could hide it.
The runtime tests verify the generated filter selections, persisted scope and
sample timing, including the rounded 100001-sample EOF case, retry and reopen.
Assigned/unassigned boundary tests retain strict positive exemptions and the zero
tail fix. Cached/uncached output parity and one shared PCM decode are verified in
both assignment modes. No PCM-cache or resource-budget safeguard was removed.

The synthetic MXF gate has two active mono mix legs and six empty ISO streams.
With all six explicitly unused, all six measured silence events remain INFO and
there is no silence WARN. Changing just stream 3 to expected yields one WARN;
streams 4-8 remain INFO. A seven-channel WAV gate detects its required silent ISO
beneath an active L/R mix while keeping unused and unknown channels distinct.
These are causal tests of runtime behavior, not a fresh original-reference replay.

## Explicit program loudness

Loudness detectors advance to 1.1.0; true peak remains 1.0.0 and physical-stream
scoped. Assigned runs retain existing raw per-stream measurements. Their threshold
exceedances remain INFO evidence with UNASSIGNED_PROGRAM_SCOPE and original profile
severity, rather than being presented as designated-program compliance.

Program measurements use only ordered explicit mono/stereo members at unity gain:
channel selection within a stream or a declared join across streams. Findings have
program scope and all physical members, with no fabricated single-stream identity.
All integrated/range/momentary/short-term program results use existing profile
thresholds. Program results and raw stream results are separately persisted in
execution metrics. No aggregate multitrack or mono-leg result is relabelled as a
stereo program result.

Before routing, an owned FFprobe process streams machine-readable decoded audio
frame timestamps/sample counts. Validation requires contiguous, nonnegative sample
clocks and matching start, sample rate and decoded coverage across program legs.
Missing frames, unknown clocks, gaps, overlaps or unequal coverage fail explicitly;
no alignment padding, offset correction, resampling or downmix is inferred. The
existing R128 analysis-window framing is unchanged. This is conservative: media
with rounded/non-contiguous timestamps may be rejected even if an operator could
construct a valid program with additional explicit alignment policy.

Clock validation is cached once per run/assignment. R128 metadata is reused across
program loudness detectors; program cache names use hashed IDs. Decoder/filter
threads and metadata buffers are bounded. Assigned runs add full-file hash passes
and a streamed clock-validation pass; no throughput-equivalence claim is made.
Legacy runs do not pay these new checks. Owned subprocess cleanup/cancellation,
source immutability and PCM storage safeguards remain in place.

Program findings retain METRICS_JSON evidence. A program waveform/spectrogram
preview is not implemented; the existing evidence-error mechanism explicitly
reports unavailable single-stream preview rather than showing the wrong leg.
Unknown activity expectations and absent program assignments are called out in
analysis/report interpretation notes. PASS still means no active WARN/FAIL under
the selected policy, not proof that unknown coverage or technical intent is clean.

## Discontinuity: tested and rejected two-sided interpolation

Production discontinuity remains 1.0.0, with unchanged thresholds and behavior.
The previous candidate-count veto remains rejected. The new bounded experiment
adds one sample of lookahead to the per-channel candidates and computes
`abs(x[n] - (x[n-1] + x[n+1]) / 2)`. It tests whether this local prediction residual
can separate a non-smooth edit from a sharp but continuous production sound, using
the existing profile-derived amplitude scale as a trial gate. It does not introduce
or tune a new production cutoff.

The trial clears the sharp, stereo-sharp, delayed-sharp and MXF-sharp negatives,
and retains masked/clustered click detections. It still flags the legitimate
`sustained_shifted` case. It also truncates the wide-click event outside its required
timestamp tolerance. Further causal positives demonstrate unsafe recall:

- `audio.discontinuity.dc_step_moderate.001`: injected 0.4 offset from 2 s onward;
  production detects its edge within one sample, while interpolation halves its
  residual below the existing amplitude scale and misses it.
- `audio.discontinuity.plateau_click.001`: injected two-sample 0.4 plateau at 2 s;
  production detects both event boundaries, while interpolation misses it.

These new recipes are version 1.5.0 and remain positive production acceptance
cases. No existing negative expectation was weakened. Diagnostic tests asserting
the rejected rule's limitations are separate from the production acceptance gate.
The rule is not promoted because discrimination gained on some sharp attacks does
not justify lost step/plateau recall, shortened evidence or the remaining negative.
A continuous waveform sampled sharply can still have a large local prediction
error; smooth recovery/low residual is not sufficient evidence of no digital fault.

## Remaining acceptance failures

The complete audio discontinuity manifest now has **22 cases: 15 PASS / 7 FAIL**.
Every remaining production failure is listed here:

| Fixture ID                                  | Remaining failure                                             |
| ------------------------------------------- | ------------------------------------------------------------- |
| `audio.discontinuity.masked.001`            | Injected click missed under shared cross-channel baseline     |
| `audio.discontinuity.masked_swapped.001`    | Same false negative with channel order reversed               |
| `audio.discontinuity.sharp.001`             | Legitimate sharp transient flagged                            |
| `audio.discontinuity.sharp_stereo.001`      | Legitimate simultaneous sharp transients flagged              |
| `audio.discontinuity.sharp_delayed.001`     | Legitimate delayed sharp transients flagged                   |
| `audio.discontinuity.sustained_shifted.001` | Legitimate attack flagged at shifted window phase             |
| `audio.discontinuity.mxf_sharp.001`         | Legitimate transient flagged on both independent mono streams |

The clustered, wide, moderate-step and plateau injected faults are all detected by
unchanged production. The MXF reference event near 7.567 s remains unresolved;
its loudness/peak measurements and accepted interpretation are not relabelled.

Previously documented video failures remain, without rerunning them:
`video.zoom_settle.001`, `video.static_between_cuts.001`,
`video.intentional_hold.001`, `video.intentional_hold_lossy.001`, and
`video.intentional_periodic_hold.001`. The original reviewed MP4 zoom interval also
remains a documented duplicate/cadence false positive. Its known image-only intent
ambiguity is preserved; no further video heuristics or temporal-expectations
architecture were attempted.

## Focused validation

Commands executed for this increment include:

```powershell
.venv/Scripts/python.exe -m pytest engine/tests/test_audio_runtime.py engine/tests/test_audio_program_clock.py engine/tests/test_audio_applicability_contract.py engine/tests/test_discontinuity_shape_probe.py -q --tb=short
.venv/Scripts/python.exe -m pytest engine/tests/test_audio_runtime.py engine/tests/test_audio_program_clock.py -q --tb=short
.venv/Scripts/python.exe -m pytest engine/tests/test_audio_calibration.py engine/tests/test_audio.py engine/tests/test_acceptance.py -k 'calibration or silence or discontinuity_isolated or current_profile_document or shared_pcm or loudness_numeric or windowed_loudness or silent_integrated' -q --tb=short
.venv/Scripts/python.exe -m pytest engine/tests/test_audio_calibration.py engine/tests/test_audio.py -k 'silence_edge_contract or shared_pcm' -q --tb=short
.venv/Scripts/python.exe -m pytest engine/tests/test_projects.py engine/tests/test_ai.py engine/tests/test_batches.py engine/tests/test_ipc.py -k 'canonical_schema or migration or capabilities_are_truthful' -q --tb=short
.venv/Scripts/python.exe -m pytest engine/tests/test_jobs.py -q --tb=short
```

- Final runtime and program-clock selection: **19 passed**, including stale-source
  rejection, assignment retry/reopen, source immutability, MXF role switches,
  migration rollback/history preservation, cache reuse and invalid clock rejection.
- Initial runtime/clock/contract/experiment selection: **83 passed**. Subsequent
  MXF role-switch and schema-4 rollback/history tests: **3 passed**.
- Focused production audio gate: **51 passed / 7 failed / 100 deselected**; only
  the seven listed discontinuity gaps fail.
- Added assigned/unassigned silence boundary and shared-PCM checks: **26 passed /
  119 deselected**. These include overlap with the preceding selection; counts
  should not be summed as unique tests.
- Schema, legacy migration and capabilities selection: **5 passed / 127 deselected**.
- Changed run-start/retry orchestration suite: **19 passed**.
- Ruff lint/format and strict mypy pass for the 24 touched Python files. Prettier
  passes for changed documentation/manifests/policy JSON; `git diff --check` passes.
  `node --test tests/repository.test.mjs` passes all **3** small specification/
  repository checks, including authoritative manifest byte counts.

No full quality gate, Windows build, packaging, installer/portable generation,
commit, push, merge or PR was performed. Source reference media and historical
reference results remain untouched.

Phase 12 is **not ready for full validation**: the seven audio discrimination
failures and accepted video ambiguity remain explicit failing gates. Runtime
applicability is now functional for explicitly assigned single-file runs, with the
UI/batch and program-preview limitations above. A safe discontinuity correction
still needs independent reviewed transient material and a contextual discriminator
that retains all injected defects and event timing. Do not promote a partial
heuristic or weaken these acceptance gates to declare calibration complete.
