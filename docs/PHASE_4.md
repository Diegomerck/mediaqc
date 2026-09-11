# Phase 4 — deterministic audio QC

Phase 4 extends the Phase 3 sequential detector/job contract, cancellation token,
owned-process registry, canonical SQLite tables and JSON-lines IPC. It registers
all 14 audio detector IDs. No authoritative specification or database schema was
changed. There are no video detectors, AI, reports, playback, timeline, disposition
editor or waveform/spectrogram viewer in this phase.

## Measurement algorithms

- Integrated, short-term, momentary and range loudness use bundled FFmpeg EBU R128
  metadata, including its K weighting, absolute/relative gating and LRA calculation.
  Short-term windows are 3 s, momentary windows 400 ms, with 100 ms updates.
  Bounds are strict; an exact threshold passes. Events must meet profile duration.
  Partial final windows are padded only in the measurement pipe; reported event
  ends are limited to stream duration. No block surviving the absolute gate yields
  `NO_GATED_AUDIO` and a null integrated measurement. Insufficient window duration
  yields `INSUFFICIENT_DURATION` rather than a fabricated metric.
- True peak uses FFmpeg EBU R128 oversampling. A separate measurement pass adds
  100 ms of digital silence to the decode pipe to flush reconstruction and the
  metadata frame containing the final samples, including sub-100 ms sources.
  This never writes or changes the source. Sample peaks measure native decoded
  float samples per channel. A numerical -300 dB floor represents exact zero
  without non-JSON infinity; it is not a QC threshold.
- Clipping counts near-full-scale samples per channel and preserves consecutive
  runs across decode chunks. Profile gap tolerance merges runs; an event requires
  the configured minimum consecutive count. Findings describe clipping evidence,
  without claiming audible distortion.
- Silence uses 10 ms RMS windows over all channels, with minimum duration and
  head/tail exemptions. An event touching an exempt edge interval is exempted as
  a whole. Its severity is profile policy, including INFO.
- Imbalance compares whole-stream RMS for explicitly configured channel pairs.
  Phase uses mean-centered normalized correlation in 50 ms windows; undefined
  correlation for silent/constant channels produces no negative-phase finding.
  Missing configured pairs return `NOT_APPLICABLE`, including ordinary mono.
- Hum uses Hann-windowed 1 s spectra with 50% overlap, independently tests each
  configured harmonic against neighboring spectral energy, then requires family
  energy and persistence gates. It measures each channel's spectral power before
  averaging, so opposite-polarity channels cannot cancel a hum measurement.
- Noise floor uses overlapping 100 ms windows (50 ms hop), an exact-count fixed
  histogram with 0.1 dB quantization, the profile quiet percentile and absolute
  quiet gate, and spectral-flatness gating to reject tonal programme material.
  A second bounded pass estimates RMS from selected broadband quiet windows.
  Quiet duration counts the union of overlapping windows. Amount and level
  stability determine confidence. Insufficient or unstable evidence returns
  `INSUFFICIENT_QUIET_REGIONS`, a null estimate and a persisted detector warning.
- Dropout evaluates each channel separately using 1 ms energy windows and independently requires active pre-gap and
  post-gap context. Profile min/max duration distinguishes short gaps from
  sustained silence. Head/tail gaps without both contexts are not candidates.
- Discontinuity uses a 20 ms local median absolute derivative as context, with
  profile absolute jump, relative derivative and sensitivity gates. It groups
  nearby isolated jumps, including chunk boundaries, and reports measured ratios
  with confidence. Default severity is WARN.

The FFT and array calculations use NumPy. NumPy 2.4.1 and SciPy 1.17.0 are pinned
and bundled as the specified numerical runtime; FFmpeg supplies EBU measurement.
DSP stays in Python, without UI signal processing or remote services.

## Profiles and compatibility

`general_technical_qc` 1.1.0 adds explicit policy for spectral quiet-region gating,
hum harmonic/family gates, dropout context and discontinuity gates. Existing 1.0.0
values remain available in their original document; distributed thresholds were
not silently overwritten. The UI selects 1.1.0. Older 1.0.0 requests/retries remain
accepted and retain their exact historical snapshots. For newly introduced gates
absent from a 1.0.0 snapshot, detector version 1.0.0 uses the distributed 1.1.0 gates;
the full effective section is saved with every finding and its evidence.

Profile validation rejects invalid numeric types, non-finite values, inverted
bounds, bad channel indices/pairs, invalid counts and out-of-range policy values.
Disabled detectors never execute. A source without supported audio cannot produce
a false PASS. Profile editing remains outside this phase's UI.

## Persistence, evidence and UI

Orchestration persists returned findings with canonical detector/stream IDs,
versions, severity, intervals, measurements, thresholds and profile identity.
Each finding gets a `METRICS_JSON` artifact under
`evidence/audio/<run-id>/<finding-id>.json`. A write failure is explicit in
`metadata.evidence_error`; the underlying finding is retained. Phase 6's rendered
waveform/spectrogram evidence and inspector are not implemented here.

`analysis.get` includes persisted measurements, warnings, result counts and the
first finding page. `finding.list` supports run, severity, detector, disposition
and overlapping time filters, with up to 100 results per page; `finding.get`
returns a saved finding and evidence references. The existing desktop allowlist
and event reader now accept these two methods and `analysis.finding_created`.
Completed runs derive PASS/WARN/FAIL from persisted, active findings. Cancelled
or failed runs have no overall result. Historical runs survive retry/reopen.

The React view shows the selected profile, result/counts, detector state and raw
measurements/warnings, expandable findings, thresholds, confidence and project
evidence paths. It can load more findings without an unbounded IPC response.

## Resources and cancellation

Custom DSP decodes native-rate float64 PCM in bounded windows without a full-file
copy or full decoded audio in RAM. Detectors run sequentially, with additional
decode passes for individual algorithms. Loudness metadata is cached as JSONL in
the run's project cache and shared by the four loudness metrics; true peak has a
separate cache because it needs filter-tail flushing. Cache size grows with
duration; it contains measurements, not a media copy, and is retained per run.
Returned finding lists naturally grow with the number of detected events.

The existing process registry owns every FFmpeg child. A concurrent bounded stderr
drainer prevents blocked pipes. Cancellation stops work, kills/reaps owned tools,
rolls back a cancelled persistence transaction and uses Phase 3 terminal handling.
Decode errors retain a bounded stderr excerpt and detector-specific project log.
The source is opened only as input; no source rename, rewrite, metadata edit or
adjacent sidecar is performed.

## Regression and release validation

`npm run fixtures:audio` reproduces the eleven required copyright-free fixtures
from `tests/fixtures/manifests/audio.json`. Tests execute the manifests and also
cover all-detector clean controls, numeric/threshold boundaries, insufficient
duration/evidence, mono/stereo/multichannel behavior, intersample peaks, final
partial frames, clipping continuity/counts, silence exemptions, 50/60 Hz hum,
noise confidence, dropout duration limits, discontinuities, malformed PCM/media,
real-process cancellation, canonical persistence, IPC, reopen and immutability.

Most event tolerances are 1–10 ms or the specified 50 ms. EBU loudness updates have
100 ms resolution and hum has a 1 s spectral window with 500 ms hops; their tests
explicitly document these windowing tolerances. Whole-stream LUFS uses 0.15 LU
numeric tolerance on a known tone; gated-tone comparison allows 0.4 LU for boundary
blocks. Broadband noise estimates use 0.15 dB tolerance.

`npm run check` now has 21 gates, retaining every previous gate and adding
`phase4:smoke`. It actually builds the Windows Tauri release executable and bundled
runtime. Phase 1 engine/native, Phase 2 inspection and Phase 3 lifecycle smoke tests
remain. Phase 3's obsolete empty-registry expectation now checks completed audio
execution while retaining cancellation, retry, events, restart and history checks.
Phase 4 smoke uses a defect fixture through the production native controller with
empty PATH, checks FAIL aggregation, findings/evidence IPC and source hashes/mtime.

Recorded clean speech/music and clean-machine Windows 10/11 validation are not
available in this repository. Synthetic regressions do not establish the curated
real-programme 30-minute heuristic false-positive budget. Hum, noise, dropout and
discontinuity remain conservative technical candidates, without broadcast
compliance or audibility claims. Installer/signing validation remains Phase 9.
