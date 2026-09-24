# Phase 10 focused performance and loudness interpretation changes

## Implementation

- Video timestamp ffprobe uses four decoder threads within the one active file.
  Original frame timestamps remain unchanged; the earlier RGB DTS fix remains.
- PCM detectors share a run-local float64 decode. I/O is streamed in bounded
  blocks; the cache has a 1 GiB project-wide disk budget, including abandoned
  partial files. Streams known to exceed available budget bypass caching;
  underestimated streams stop caching at the limit and continue direct decode.
  Unavailable cache storage falls back to direct decode. Completed-cache read
  errors are explicit failures rather than silently restarting midway through a
  detector. No source-file copy is made. Derived PCM cache files are removed on
  terminal cleanup and during recovery under the project lease. The two R128
  passes retain their different framing/tail handling and existing metadata reuse.
- Dropout window powers are computed in batches of 256 original windows. Sample
  boundaries, reduction results, thresholds, per-channel state machines, and
  finding timestamps are unchanged. Detector execution remains sequential.
- `analysis.get.interpretation_notes` qualifies undeclared multichannel layouts
  and unknown grouping of multiple audio streams using persisted stream metadata.
  The selected-file view displays notes outside Technical Details; detailed HTML/
  PDF and batch summaries include them. Measurements, thresholds, dispositions,
  and verdicts are not altered. No channel assignment or program mix is invented.

## Focused validation

- Initial PCM equivalence/cancellation/storage checks: 7 passed.
- Expanded affected regression selection: 21 passed, 67 deselected. This covers
  PCM reuse against uncached results for nine PCM detectors; exact power windows
  at 44.1/48 kHz including seven channels and partial tails; clipping, silence,
  channel pairs, dropout/discontinuity/noise boundaries; cancellation; malformed
  samples; budget exhaustion; early close; decode failure; recovery cleanup;
  serial/threaded timestamp equivalence; actual video batch completion; and
  persisted loudness notes in result summaries and HTML/PDF exports.
- Focused frontend `AudioResults.test.tsx`: 8 passed, including prominent notes
  with the original FAIL verdict and Technical Details still collapsed.
- Changed-file Ruff lint/format and strict mypy; frontend ESLint and TypeScript.
  A cache-storage test annotation and formatting issues found by these checks
  were corrected without changing runtime measurements.

The relevant Python selection was:

```text
python -m pytest engine/tests/test_audio.py engine/tests/test_reports.py engine/tests/test_video_pipeline.py -k "shared_pcm or vectorized_power or pcm_budget or pcm_storage or clipping_cross or silence_boundaries or pair_selection or dropout_duration or discontinuity_isolated or single_channel_dropout or noise_quiet or cancel_real_decode or pcm_incomplete or loudness_scope or rawvideo_mux" -q
```

## Four-file comparison

The four original reference sources were analyzed once as a folder batch with
General Technical QC 1.2.0, AI OFF, using the current engine in a separate project
under `.cache/phase10-performance-after`. The user's project was read only.

| Stage                     | Saved installed-app run | Current engine run |
| ------------------------- | ----------------------: | -----------------: |
| Entire batch              |                 358.7 s |            238.3 s |
| Video cache construction  |                 199.3 s |            128.3 s |
| All audio detectors       |                 143.8 s |             90.0 s |
| Dropout (subset of audio) |                  33.6 s |              8.4 s |

Total observed reduction: approximately 120.4 seconds / 33.6%. This compares a
saved installed-app run with a development-engine run on the same sources and
machine, not a controlled release benchmark or a promised installed-app speed.
The first PCM-consuming detector bears cache-write cost; subsequent detectors
reuse it. Observed peak PCM disk use was 594,642,048 bytes, below 1 GiB; no PCM
cache files remained after completion. RAM buffers remain independent of source
duration; this pass did not repeat a large-file memory benchmark.

All four files completed with zero ERROR. Verdicts remained MP3 WARN, WAV WARN,
MP4 WARN, MXF FAIL. All 11 findings matched detector/stream, severity, timeline,
measurements and saved thresholds (numeric comparison tolerance 1e-9). Synthetic
PCM equivalence also compared all result metrics exactly. Source identity checks
before/after matched. WAV results now disclose the unknown seven-channel layout;
MXF results disclose independent-stream measurement and unknown program grouping.

Evidence: `.cache/phase10-performance-after.json`, its adjacent log, and the
separate validation project. These are ignored local diagnostics. This focused
development comparison preceded the release validation recorded below.

## Manual installed-app benchmark — 2026-09-24

The operator reported a successful four-file batch in the newly packaged and
installed Windows build, using General Technical QC 1.2.0 with AI OFF:

- `MP3 TEST 1.mp3`
- `WAV TEST 1.wav`
- `MP4 TEST 1.mp4`
- `MXF TEST 1.MXF`

Reported local start: **11:08:30**; end: **11:12:00**; elapsed: **210.0 seconds
(3:30)**. All four files completed successfully. This is operator-observed
installed-application wall time, not instrumented detector-stage timing or a
controlled/repeated benchmark. Cache state, background load, and timing precision
were not controlled. Do not attribute the difference from the development run
solely to packaging or infer a universal speedup.

| Run                          | Elapsed | Measurement context                                         |
| ---------------------------- | ------: | ----------------------------------------------------------- |
| Original installed build     | 358.7 s | Saved original installed-app batch                          |
| Optimized development engine | 238.3 s | Separate diagnostic project; instrumented engine run        |
| Optimized installed build    | 210.0 s | Operator-reported manual timing of the same four-file batch |

The installed-to-installed observed reduction is **148.7 seconds, approximately
41.5%**. Successful processing does not mean a PASS QC verdict. The manual timing
report did not independently re-audit every finding; the earlier development
comparison preserved all 11 findings within numeric tolerance.

No detector thresholds or profile values were recalibrated. These four sources
are initial operator-designated clean references, not a sufficient calibration
corpus. Loudness/peak, duplicate-frame/cadence, and discontinuity findings still
require separate detector/profile assessment using a larger known-good/known-bad
corpus. Unknown channel layouts and program grouping remain explicitly qualified;
no definitive program-compliance claim is inferred from per-stream loudness.

## Release validation and remaining acceptance

The full gate ran once: 21/22 stages initially passed, including 330 Python tests,
44 frontend tests, 3 baseline tests, 6 Rust unit tests, and 12 Rust integration
tests. The only failure was Prettier on 14 CRLF working-tree files. With the
repository's explicit configuration, all 14 pass in HEAD; no Phase 10 semantic
edit caused the failure. LF normalization and the formatting-only rerun passed.
The other successful stages, including engine/frontend/Windows release builds,
were retained rather than repeated. All 22 gate requirements are now satisfied
across that run and the targeted formatting rerun.

NSIS and portable packaging passed. Relocated portable acceptance passed WAV,
MP3, MP4, MXF, corrupt media, cancellation/retry, persistence/reopen, evidence,
dispositions, HTML/PDF, unavailable-AI fallback, and source hash/size/timestamp
checks with empty PATH/PYTHONPATH. All 311 manifest entries and the ZIP checksum
matched. Embedded engine bytecode matched the current PCM cache, ffprobe threading,
dropout, loudness qualification, reporting, and cleanup code. See
[Phase 10 validation](PHASE_10_VALIDATION.md) for current artifact identities.

Still outstanding: clean Windows 10/11 installation/uninstallation/reinstallation
and project/source retention; WebView2 present/absent cases; firewall-enforced
offline operation; physical CPU-only acceptance; remaining interactive and
long-running resource checks; and the future known-good/known-bad detector corpus.
The manual timing result does not close those acceptance items. Performance work
is ready for commit review; complete clean-machine release acceptance remains open.
