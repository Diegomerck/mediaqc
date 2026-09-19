# Phase 5 — recorded clean-video validation

Validation date: 2026-09-18. **Recorded video acceptance: PASS on the supplied corpus.**

The owner manually reviewed and designated these four external files as clean video.
All 13 video detectors completed for every file (52 executions), with zero video
findings at any severity. No detector, profile, threshold, production code or
authoritative specification changed for this validation.

## Exact acceptance criterion

From [Testing specification §9](../specs/09_TESTING_SPEC.md), for
`general_technical_qc` on curated clean corpus:

- deterministic integrity/threshold detectors: zero unexplained false positives;
- heuristic visual anomaly/flash/freeze: target <= 1 false WARN per 30 minutes of representative clean content.

Observed: zero deterministic video false positives and zero visual-anomaly/flash/freeze
WARN findings over **195.028167 seconds (03:15.028)**. The observed normalized rate
is **0 false WARN per 30 minutes**. This closes the previously unverified recorded-video
budget check on this corpus. It is a small 3.25-minute sample, not a 30-minute
recording or statistical assurance for other content. Scene-type coverage was not
independently catalogued. No synthetic footage or repeated loops inflated duration.

The separate audio dropout/discontinuity budget is outside this Phase 5 video
acceptance exercise. Audio candidates remain intact and unadjudicated.

## Media and production execution

External source directory: `C:\MediaQC-Test-Media\Clean`. The originals were not
copied into the repository or modified. All are MXF, H.264, 3840 × 2160,
24000/1001 fps (23.976024), `yuv422p10le` (10-bit 4:2:2). Embedded audio is 48 kHz,
24-bit PCM (`pcm_s24le`), in separate mono streams. Video-stream bitrate was
unavailable; the table gives container bitrate.

| Clip | Filename                                   | Duration (s) | Container Mbps | Video / audio streams | Decoded frames |
| ---- | ------------------------------------------ | -----------: | -------------: | --------------------- | -------------: |
| 1    | `INFAM_31_51_PROT1_PORT16_11_D40_U11B.MXF` |    39.205833 |        240.792 | 1 / 8 mono            |            940 |
| 2    | `INFAM_32_2_T1_PORT16_13_D40_U11B.MXF`     |    29.863167 |        241.139 | 1 / 8 mono            |            716 |
| 3    | `INFAM_34_15A_T2_PORT16_2_D40_U11B.MXF`    |    64.898167 |        241.116 | 1 / 8 mono            |           1556 |
| 4    | `INFAM_45_18_T2_A001_02_D46_DS.MXF`        |    61.061000 |        396.335 | 1 / 4 mono            |           1464 |

The first three files also contain SMPTE 436M ancillary data and report BT.709
transfer; the fourth does not report a transfer function. There were no metadata
inspection failures. Full production decode-integrity passes reported no decode
errors, frame-count mismatches or incomplete durations. All files were usable.

Executed the Windows release-bundled `resources/engine/mediaqc-engine.exe` via
normal JSON-lines IPC (`media.inspect`, `analysis.start`, `analysis.get`,
`finding.list`), with bundled FFmpeg/ffprobe 8.1.2, AI OFF and unmodified
`general_technical_qc` 1.2.0. The returned profile exactly matched the current
distributed JSON. All enabled audio and video detectors ran normally; there was
no special profile or detector-only shortcut.

All four runs completed. Their overall application result is **FAIL due to audio
true-peak findings**, not video findings. Passing video acceptance does not mean
passing all audio delivery-policy thresholds.

## Video findings by detector

| Detector                    | Clip 1 | Clip 2 | Clip 3 | Clip 4 |
| --------------------------- | -----: | -----: | -----: | -----: |
| `video.decode_integrity`    |      0 |      0 |      0 |      0 |
| `video.frame_rate`          |      0 |      0 |      0 |      0 |
| `video.timestamp_integrity` |      0 |      0 |      0 |      0 |
| `video.black_frame`         |      0 |      0 |      0 |      0 |
| `video.near_black_frame`    |      0 |      0 |      0 |      0 |
| `video.freeze`              |      0 |      0 |      0 |      0 |
| `video.duplicate_frame`     |      0 |      0 |      0 |      0 |
| `video.frame_cadence`       |      0 |      0 |      0 |      0 |
| `video.luminance_anomaly`   |      0 |      0 |      0 |      0 |
| `video.flash`               |      0 |      0 |      0 |      0 |
| `video.exposure_anomaly`    |      0 |      0 |      0 |      0 |
| `video.color_anomaly`       |      0 |      0 |      0 |      0 |
| `video.visual_anomaly`      |      0 |      0 |      0 |      0 |

Every state above is COMPLETED. There are no video finding timestamps or finding
evidence because no video candidates were generated. Ordinary frame counts,
dimensions, rates and interval bounds remain in saved execution metrics. No video
finding was suppressed, ignored or marked false positive.

## Retained audio findings and source characteristics

Loudness deviations compare against the default −23 LUFS target; they do not
establish defective recording. Positive reconstructed true peaks and near-full-scale
sample peaks are measured technical properties. Digital silence was measured on six
mono tracks in clips 2 and 3 and one in clip 4. Audio discontinuities remain
unadjudicated candidates; neither audible defects nor audio false positives are
claimed. No disposition was changed.

| Clip | Detector                    | Severity | Findings |
| ---- | --------------------------- | -------- | -------: |
| 1    | `audio.discontinuity`       | WARN     |        2 |
| 1    | `audio.loudness.integrated` | WARN     |        2 |
| 1    | `audio.sample_peak`         | WARN     |        1 |
| 1    | `audio.true_peak`           | FAIL     |        1 |
| 2    | `audio.discontinuity`       | WARN     |        1 |
| 2    | `audio.loudness.integrated` | WARN     |        2 |
| 2    | `audio.sample_peak`         | WARN     |        1 |
| 2    | `audio.silence`             | WARN     |        6 |
| 2    | `audio.true_peak`           | FAIL     |        1 |
| 3    | `audio.discontinuity`       | WARN     |        1 |
| 3    | `audio.loudness.integrated` | WARN     |        2 |
| 3    | `audio.sample_peak`         | WARN     |        1 |
| 3    | `audio.silence`             | WARN     |        6 |
| 3    | `audio.true_peak`           | FAIL     |        1 |
| 4    | `audio.loudness.integrated` | WARN     |        3 |
| 4    | `audio.silence`             | WARN     |        1 |
| 4    | `audio.true_peak`           | FAIL     |        1 |

Complete retained findings follow. Stream numbers are original ffprobe indices.
All dispositions are OPEN and all findings have METRICS_JSON evidence. Complete
evidence references and effective thresholds are in `results.json` and the project
database. Times are seconds; whole-stream measurements have null timelines.

| Clip | Stream | Detector                    | Severity | Start–end (s)      | Measurements                                                                                         |
| ---- | -----: | --------------------------- | -------- | ------------------ | ---------------------------------------------------------------------------------------------------- |
| 1    |      1 | `audio.loudness.integrated` | WARN     | whole stream       | `{"integrated_lufs":-29.034,"target_lufs":-23.0,"deviation_lu":-6.033999999999999}`                  |
| 1    |      2 | `audio.sample_peak`         | WARN     | whole stream       | `{"sample_peak_dbfs":-0.010609369388011637,"channel":0}`                                             |
| 1    |      2 | `audio.loudness.integrated` | WARN     | whole stream       | `{"integrated_lufs":-24.622,"target_lufs":-23.0,"deviation_lu":-1.6219999999999999}`                 |
| 1    |      2 | `audio.true_peak`           | FAIL     | whole stream       | `{"true_peak_dbtp":0.7962110829670077,"per_channel_dbtp":{"true_peaks_ch0":0.7962110829670077}}`     |
| 1    |      1 | `audio.discontinuity`       | WARN     | 7.565792–7.566750  | `{"derivative_ratio":21.31374677028312,"context_window_seconds":0.02,"sensitivity":0.7}`             |
| 1    |      2 | `audio.discontinuity`       | WARN     | 7.566854–7.569104  | `{"derivative_ratio":84.27901700456816,"context_window_seconds":0.02,"sensitivity":0.7}`             |
| 2    |      2 | `audio.loudness.integrated` | WARN     | whole stream       | `{"integrated_lufs":-20.035,"target_lufs":-23.0,"deviation_lu":2.965}`                               |
| 2    |      1 | `audio.loudness.integrated` | WARN     | whole stream       | `{"integrated_lufs":-21.829,"target_lufs":-23.0,"deviation_lu":1.1709999999999994}`                  |
| 2    |      2 | `audio.true_peak`           | FAIL     | whole stream       | `{"true_peak_dbtp":1.1380970267294512,"per_channel_dbtp":{"true_peaks_ch0":1.1380970267294512}}`     |
| 2    |      2 | `audio.sample_peak`         | WARN     | whole stream       | `{"sample_peak_dbfs":-0.010609369388011637,"channel":0}`                                             |
| 2    |      7 | `audio.silence`             | WARN     | 0.000000–29.863167 | `{"rms_dbfs":-300.0,"threshold_dbfs":-60.0,"duration_seconds":29.863166666666665}`                   |
| 2    |      5 | `audio.silence`             | WARN     | 0.000000–29.863167 | `{"rms_dbfs":-300.0,"threshold_dbfs":-60.0,"duration_seconds":29.863166666666665}`                   |
| 2    |      8 | `audio.silence`             | WARN     | 0.000000–29.863167 | `{"rms_dbfs":-300.0,"threshold_dbfs":-60.0,"duration_seconds":29.863166666666665}`                   |
| 2    |      6 | `audio.silence`             | WARN     | 0.000000–29.863167 | `{"rms_dbfs":-300.0,"threshold_dbfs":-60.0,"duration_seconds":29.863166666666665}`                   |
| 2    |      3 | `audio.silence`             | WARN     | 0.000000–29.863167 | `{"rms_dbfs":-300.0,"threshold_dbfs":-60.0,"duration_seconds":29.863166666666665}`                   |
| 2    |      4 | `audio.silence`             | WARN     | 0.000000–29.863167 | `{"rms_dbfs":-300.0,"threshold_dbfs":-60.0,"duration_seconds":29.863166666666665}`                   |
| 2    |      2 | `audio.discontinuity`       | WARN     | 1.697104–1.699604  | `{"derivative_ratio":1847.948416988417,"context_window_seconds":0.02,"sensitivity":0.7}`             |
| 3    |      1 | `audio.loudness.integrated` | WARN     | whole stream       | `{"integrated_lufs":-28.341,"target_lufs":-23.0,"deviation_lu":-5.341000000000001}`                  |
| 3    |      2 | `audio.sample_peak`         | WARN     | whole stream       | `{"sample_peak_dbfs":-0.010609369388011637,"channel":0}`                                             |
| 3    |      2 | `audio.loudness.integrated` | WARN     | whole stream       | `{"integrated_lufs":-20.623,"target_lufs":-23.0,"deviation_lu":2.376999999999999}`                   |
| 3    |      2 | `audio.true_peak`           | FAIL     | whole stream       | `{"true_peak_dbtp":0.4403147963544056,"per_channel_dbtp":{"true_peaks_ch0":0.4403147963544056}}`     |
| 3    |      7 | `audio.silence`             | WARN     | 0.000000–64.898167 | `{"rms_dbfs":-300.0,"threshold_dbfs":-60.0,"duration_seconds":64.89816666666667}`                    |
| 3    |      5 | `audio.silence`             | WARN     | 0.000000–64.898167 | `{"rms_dbfs":-300.0,"threshold_dbfs":-60.0,"duration_seconds":64.89816666666667}`                    |
| 3    |      8 | `audio.silence`             | WARN     | 0.000000–64.898167 | `{"rms_dbfs":-300.0,"threshold_dbfs":-60.0,"duration_seconds":64.89816666666667}`                    |
| 3    |      4 | `audio.silence`             | WARN     | 0.000000–64.898167 | `{"rms_dbfs":-300.0,"threshold_dbfs":-60.0,"duration_seconds":64.89816666666667}`                    |
| 3    |      3 | `audio.silence`             | WARN     | 0.000000–64.898167 | `{"rms_dbfs":-300.0,"threshold_dbfs":-60.0,"duration_seconds":64.89816666666667}`                    |
| 3    |      6 | `audio.silence`             | WARN     | 0.000000–64.898167 | `{"rms_dbfs":-300.0,"threshold_dbfs":-60.0,"duration_seconds":64.89816666666667}`                    |
| 3    |      2 | `audio.discontinuity`       | WARN     | 2.447500–2.448250  | `{"derivative_ratio":30.96913251110834,"context_window_seconds":0.02,"sensitivity":0.7}`             |
| 4    |      4 | `audio.loudness.integrated` | WARN     | whole stream       | `{"integrated_lufs":-25.898,"target_lufs":-23.0,"deviation_lu":-2.8979999999999997}`                 |
| 4    |      1 | `audio.true_peak`           | FAIL     | whole stream       | `{"true_peak_dbtp":-0.10486110824743766,"per_channel_dbtp":{"true_peaks_ch0":-0.10486110824743766}}` |
| 4    |      1 | `audio.loudness.integrated` | WARN     | whole stream       | `{"integrated_lufs":-29.864,"target_lufs":-23.0,"deviation_lu":-6.864000000000001}`                  |
| 4    |      3 | `audio.loudness.integrated` | WARN     | whole stream       | `{"integrated_lufs":-25.898,"target_lufs":-23.0,"deviation_lu":-2.8979999999999997}`                 |
| 4    |      2 | `audio.silence`             | WARN     | 0.000000–61.061000 | `{"rms_dbfs":-98.79260083371526,"threshold_dbfs":-60.0,"duration_seconds":61.061}`                   |

## Integrity and reproducibility

Streaming SHA-256 hashes were computed before inspection and again after all
analysis. Complete-file hashes, sizes and nanosecond modification times matched
for every source. No source rename, metadata edit, transcode, sidecar or copy occurred.

| Clip |      Bytes | SHA-256 before = after                                             | Run ID                                 |
| ---- | ---------: | ------------------------------------------------------------------ | -------------------------------------- |
| 1    | 1180056624 | `e62273d9972f2d59c90d81387a6e003b3c44f0daad3973a1d90e69ada217a508` | `7337cb01-45b1-4f21-974b-4ce8e0b4770f` |
| 2    |  900146224 | `48e701e4e8e890f4f4817785c6112a0b28882630efb5b9223df68271bbe276c2` | `afc99f7a-03d6-4beb-b823-03737ce38970` |
| 3    | 1955996720 | `152a2a510c6172d9bc36c7be82f4f6eaf80df4c0edbbde55bcbdf8a35f823bea` | `409e4d96-8702-4d74-915d-52a355efbbd9` |
| 4    | 3025072688 | `b4d815b0fd8e21fa331e914289e69dc4c4b8579d053efc87915661f97b7ef93e` | `25259ee6-c37a-4efa-832b-d12039336b41` |

Local validation artifacts are retained under `.cache/phase5-clean-corpus-20260918/`
(ignored by Git):

- `preflight.json`: full probe metadata and pre-analysis source fingerprints.
- `profile.json`, `capabilities.json`: exact policy and bundled tool versions.
- `results.json`: complete runs, detector statuses/metrics, findings, evidence references and before/after hashes.
- `project/project.sqlite`, `project/evidence/`: canonical persistence and evidence.
- `events.jsonl`, `engine-stderr.log`, `validation.log`: event and diagnostic records.
- `validate.py`: packaged-engine validation harness; no production-code changes.

To reproduce, verify the same external-file hashes and use the packaged engine
with profile 1.2.0 in a fresh output project outside the source directory. Inspect
and start one normal run per file, await terminal states, fetch all findings pages,
check all 13 video execution states, and compare hashes afterwards. Do not reuse an
existing project.create destination or count replayed footage as added coverage.

The existing complete 22-gate verification, 224 passing tests, Windows release build
and packaged smoke results were not rerun: this validation changed documentation
only. Targeted documentation formatting and diff checks apply. No Phase 6+ work
was added.
