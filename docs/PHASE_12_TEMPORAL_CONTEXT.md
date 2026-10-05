# Phase 12 — temporal context follow-up, 2026-09-27

**No production correction accepted.** This continues the earlier
[duplicate/cadence investigation](PHASE_12_REPEAT_INVESTIGATION.md); its evidence,
negative expectations, reports and two acceptance failures are retained. The new
work identifies a missing signal, rather than another similarity threshold.

## Evidence reused and measurements added

The six retained clips for zoom settling, static insert, single duplicate,
lossy single duplicate, periodic cadence fault and low motion were reused without
regeneration. Their SHA-256 hashes match the earlier acceptance report. The
reviewed original MP4 was opened read-only for a bounded 192-frame temporal
probe, not another full-file detector replay. Its full source hash matches the
earlier reference report; size and mtime were unchanged by the probe. No old
report, annotation, source, or project database was rewritten.

`tools/repeat_temporal_probe.py` records original PTS/durations, adjacent RGB,
histogram and hash measurements, lag-2/lag-3 RGB differences, adjacent signed
residual cosine, and global translation phase-correlation estimates. These are
developer measurements, not defect decisions. Translation is a restricted model:
it cannot model a zoom, and repetitive texture gives ambiguous displacement.
The raw phase-correlation response is not a probability or a calibrated confidence.

The probe retains three previous 320×180 RGB frames plus the current frame,
streams through the existing owned-process API, and caps requests at 512 frames.
Frame/PTS pairing errors fail explicitly. It checks source SHA-256/size/mtime
before and after, and cancels/reaps owned processes in `finally`. Measurement
reports contain numbers, not extracted media content.

## Temporal hypotheses evaluated

| Hypothesis                                                                  | Evidence                                                                                                                                                                                                                                                           | Conclusion                                                                                                                                                         |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| A skipped temporal step is followed by larger recovery motion               | Synthetic legitimate zoom: adjacent differences 0.031136 → 0.000028 → 0.059012. Genuine single duplicate: 0.071716 → 0 → 0.131569. Lossy duplicate: 0.070839 → 0.000585 → 0.130935.                                                                                | Both legitimate settling and injected replacement show pause/catch-up. A larger recovery step is insufficient. These are RGB differences, not physical velocities. |
| Global translation trajectory separates cases                               | The periodic stripe fixture has low/ambiguous phase-correlation responses and occasional displacement aliases. Lossy encoding can change the inferred displacement despite unchanged underlying motion. The reviewed MP4 is a zoom, outside the translation model. | Do not turn these vectors or response values into a suppression rule.                                                                                              |
| Scene continuity/cut context identifies the static insert                   | At the first static-insert boundary, histogram divergence is 0.025 and hash similarity is 1.0; adjacent ordinary motion has divergence 0.034375. The outgoing boundary is stronger (0.128125 / 0.5).                                                               | A threshold on existing scalar descriptors does not reliably identify both boundaries. Cut adjacency alone is not an exemption.                                    |
| Cut-adjacent repeats should be ignored                                      | A new genuine copied frame immediately before a cut is detected at 0.96–1.04 s by both detectors.                                                                                                                                                                  | A blanket cut veto loses a positive.                                                                                                                               |
| Original PTS establishes cadence inconsistency                              | The MP4 near-repeat has regular local PTS steps of 0.016655–0.016656 s. Both fault and intentional synthetic holds use regular 0.04 s steps.                                                                                                                       | Presentation timing is not an acquisition clock or proof that each displayed frame should be unique.                                                               |
| Duration, repeat count, recovery, and periodicity together establish intent | New intentional holds match positive fault clips across their complete timelines, including encoded bytes.                                                                                                                                                         | No function of those source-only observations can distinguish each paired intent.                                                                                  |

In the MP4, adjacent differences around the event are
0.020750, 0.018422, **0.000974**, 0.016083, 0.029499, 0.001625, 0.026681.
The wider context is uneven, rather than a measured constant-speed progression.
Neither assuming constant speed nor selecting a recovery-ratio cutoff is justified
by this sequence. The owner's clean zoom annotation remains ground truth; this
analysis does not reinterpret it as a defect.

## An observable limit, not a threshold problem

The added fixture recipes model two different causal histories:

- An animation intentionally holds its current image for one output interval,
  then catches up to its authored timeline (or repeats this rhythm periodically).
- A fault replaces the corresponding moving frame with its predecessor.

For three pairs, every image and PTS is identical across the entire four-second
sequence. With the same encoding recipe, the **complete MP4 SHA-256 hashes also
match**, including the lossy version:

| Intended negative           | Existing positive with identical file | SHA-256                                                            |
| --------------------------- | ------------------------------------- | ------------------------------------------------------------------ |
| `intentional_hold`          | `single_duplicate`                    | `98d6d91aa4d36c2e02c774489da81dcefa7f7cd814189823923fe5fc88671f99` |
| `intentional_hold_lossy`    | `single_duplicate_lossy`              | `80825b7590fcf9d7d45f99e5967a2ffb0e69e306dfeb6532f2933ac02d805f5b` |
| `intentional_periodic_hold` | `broken_cadence`                      | `1a30cf458a47a7bb36cece66022fe1384349d99337be1bd4b186104513e24dbc` |

The labels represent different production intent; neither is detector input.
They are deliberately an identifiability challenge, not ordinary samples that
one source-only classifier can perfectly separate. No lookahead length, optical
flow algorithm, timestamp check, or codec inspection can recover a distinction
absent from identical files. A filename/fixture-ID exception would be invalid.

This does **not** prove that heuristic specificity cannot improve on a narrower
corpus, or that the reviewed MP4 is intrinsically indistinguishable from every
fault. It does establish why satisfying all intentional-hold and fault cases
requires additional context or an explicit ambiguity policy. No measured recall
or false-positive rate for general production footage is claimed.

## Duplicate and cadence decisions should be separated

The existing shared rule identifies similarity plus surrounding change. It does
not independently establish cadence inconsistency. Sharing decode, repeat-group
measurements and bounded feature caches is appropriate; sharing the final fault
decision is not sufficient for the distinct detector claims.

- Duplicate evidence should describe image repetition, affected frames, duration,
  residual uncertainty and scene context. Image repetition does not establish
  whether a production hold was unintended.
- Cadence evidence should compare observed frame progression against an explicit
  expected temporal pattern, distinguish allowed conversion/holds, and explain
  the deviation. A second copy of the duplicate finding is not independent
  cadence evidence. Timestamp-integrity findings remain the responsibility of
  the existing timestamp detector, which is unchanged here.

## Smallest proposed extension — not implemented

The missing signal is **expected temporal progression/production intent**, and,
for definitive provenance-based checks, a trusted relationship between expected
source frames and observed output frames. Nominal/average FPS and container PTS
do not supply it. Measuring more motion may improve evidence but cannot replace it.

The smallest useful contract extension is an optional, immutable temporal
expectation in the engine's run context, scoped to a video stream. It would record
its authority/provenance, expected source-to-output cadence or frame mapping, and
declared intentional holds/conversions. It must distinguish an operator's stated
expectation from independently observed frame-origin evidence; a declaration
alone does not prove that the media violates it. An optional reference sequence
or trustworthy capture/edit provenance could supply stronger evidence when present.

Absent that context, cadence intent remains unresolved. Whether such observations
become review candidates, an insufficient-evidence measurement, or affect a new
run's verdict requires a separate contract/policy decision. No new status, profile,
default suppression, runtime intent annotation, UI, database migration, or verdict
change is introduced by this investigation. Historical results stay immutable.

If subsequent work evaluates richer motion/cut measurements, the smallest
measurement change is a versioned bounded feature window with validity/ambiguity
fields shared by the two detectors, followed by separate decisions. It does not
require another whole-file decode or unbounded history. It is **not sufficient**
to solve the identical-file intent ambiguity on its own. Requirements 14/15 of
the current request are the reason to stop before speculative production changes.

## Acceptance and focused checks

Added `video_temporal_context.json` without modifying the earlier manifest:

| New case                            | Required result                                | Observed                             |
| ----------------------------------- | ---------------------------------------------- | ------------------------------------ |
| Intentional hold                    | Clean                                          | **FAIL**, both findings              |
| Intentional hold, lossy             | Clean                                          | **FAIL**, both findings              |
| Intentional periodic hold           | Clean                                          | **FAIL**, four findings per detector |
| Genuine broken cadence, lossy       | Four correctly timed events per detector       | PASS                                 |
| Genuine duplicate just before a cut | Two-frame event at 0.96–1.04 s, both detectors | PASS                                 |

The new suite also checks full-timeline observational equivalence, rejection of
contradictory ground truth by the acceptance oracle, lag/translation measurement
on a known translation, zero-residual handling, and invalid/unbounded requests.

```powershell
.venv/Scripts/python.exe -m pytest engine/tests/test_video_temporal_context.py -q --basetemp=.cache/phase12/temporal-tests-20260927
.venv/Scripts/python.exe tools/repeat_temporal_probe.py "<existing MP4 path>" --output .cache/phase12/temporal-mp4.json
.venv/Scripts/python.exe -m ruff check tools/repeat_temporal_probe.py tools/generate_test_media/video.py engine/tests/test_video_temporal_context.py
.venv/Scripts/python.exe -m mypy tools/repeat_temporal_probe.py tools/generate_test_media/video.py engine/tests/test_video_temporal_context.py
```

The focused new suite produced **10 passed, 3 failed**. The three failures are the
intentional-hold acceptance cases; none is skipped, xfailed, or reclassified.
New positive events pass exact severity, stream, count and timing checks with the
unchanged General Technical QC 1.2.0 profile. Ruff, formatting and strict mypy pass.

The earlier **19 passed / 2 failed** result and original MP4 replay were retained,
not rerun. Their zoom/static-insert failures remain unresolved under unchanged
production code. Existing positive outcomes remain the established baseline.
The new MP4 probe confirms the same candidate pair and unchanged source identity;
it is a measurement report, not a fresh detector acceptance verdict.

Runtime detector versions, profile thresholds, algorithms and Phase 10 safeguards
are unchanged. The developer probe bounds frame history and scalar output; it adds
no runtime work or dependency. Its full source hashes add developer-only read I/O.
No performance improvement or end-user benchmark is claimed. No broad tests,
quality gate, build, packaging, installer, portable output, commit, push, merge or
PR was performed. The five combined unresolved negative cases remain reviewable.
