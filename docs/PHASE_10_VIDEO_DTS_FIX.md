# Phase 10 rawvideo DTS classification fix

## Root cause

`MediaTools.stream(reject_errors=True)` rejects nonempty FFmpeg error-level stderr
even when the child exits 0. The video feature cache previously passed source
timing through to its internal rawvideo encoder/muxer at the default output
timebase. Closely spaced source PTS can round to equal output DTS, producing
`Application provided invalid, non monotonically increasing dts to muxer` even
when all RGB frames are delivered successfully. This is an output-pipeline
diagnostic, not proof of source decode corruption or duplicate source PTS.

`features.cache` recorded that exception as a frames-stage MEDIA_UNSUPPORTED
error. Decode integrity emitted a FAIL finding, other video detectors refused
the cache marked incomplete, and their failed executions made the run/batch item
ERROR. Evidence generation happens separately; the missing preceding frame at
media start did not cause these detector failures.

## Narrow fix

Only the internal scaled RGB output uses `settb=1/1,setpts=N` and an explicit
filter encoder timebase. These ordinal output timestamps are not measurements;
raw RGB has no timing payload. Passthrough frame sync remains in place. Original
ffprobe PTS/durations still determine every measured frame time, rate, timestamp
finding, and temporal detector result. Source media, thresholds, and detector
mathematics are unchanged.

FFmpeg documents the [encoder timebase](https://ffmpeg.org/ffmpeg.html#Advanced-options)
and [setpts/settb filters](https://ffmpeg.org/ffmpeg-filters.html#setpts_002c-asetpts).
The regression uses the repository's bundled FFmpeg to verify the behavior.

No stderr filtering or blanket acceptance of exit-code-0 diagnostics was added.
Genuine decoder diagnostics, nonzero exits, truncated frames, count mismatches,
and incomplete duration still take the existing failure path. Safe detectors can
now use the complete cache; genuinely incomplete decoding still blocks them.
The evidence boundary behavior needed no production change.

## Focused validation

The new real-MP4 regression generates 25 frames with strictly increasing clustered
PTS (0, .001, .080, .081, ...). The old rawvideo command returns all 25 frames,
exit code 0, and repeated non-monotonic DTS diagnostics. Before the fix the
regression reproduced the reported frames-stage MEDIA_UNSUPPORTED classification.
After the fix it confirms:

- all frames processed with an error-free cache and original PTS retained;
- all 13 video detectors run successfully;
- valid VFR creates no timestamp finding under the default profile;
- prohibiting VFR produces timestamp findings from original intervals;
- duplicate source PTS in the measurement fixture still produces DUPLICATE_PTS,
  independently of decode integrity;
- an actual persisted one-item MP4 batch using General Technical QC 1.2.0,
  AI OFF completes with zero ERROR items and all video executions COMPLETED;
- source SHA-256 and last-write timestamp stay unchanged.

Commands run with the existing `.venv/Scripts/python.exe`:

```text
-m pytest engine/tests/test_video_pipeline.py engine/tests/test_evidence.py::test_start_of_media_missing_before_frame_is_only_evidence_metadata -q
  2 passed in 3.95s
-m pytest engine/tests/test_video.py::test_manifest[fixture0] engine/tests/test_video.py::test_manifest[fixture7] engine/tests/test_video.py::test_manifest[fixture11] engine/tests/test_video.py::test_decode_failure_cache_and_recovered_stderr -q
  4 passed in 7.13s
```

The existing fixtures cover clean video, timestamp irregularity, real compressed
packet corruption, and failed-cache dependency behavior. The new evidence test
confirms the start-of-media warning is metadata only, current/after frames remain
available, the finding is unchanged, and the completed run's verdict is unaffected.

Ruff formatting/lint and strict mypy passed for the three changed Python files.
The initial sandboxed pytest invocation could not access existing pytest cache/
temporary directories; the same focused checks were run outside the sandbox.
No full suites, benchmarks, large batches, builds, packages, downloads, or dependency
installations were performed. Prior uncommitted native IPC fixes were preserved.

## Original manual verification request

The original user MP4 was not supplied. If its only blocking condition is the
reported rawvideo muxer diagnostic, it should now complete video QC instead of
ERROR. A source PTS violation may still yield a profile-driven timestamp finding
and a completed WARN/FAIL verdict; output DTS diagnostics alone cannot establish
whether such a finding is warranted. Other genuine decode errors remain failures.

At the time of this focused fix, installed/portable artifacts did not contain it
and packaging required separate authorization. That authorization and validation
have since completed: the 2026-09-24 installer/portable release includes the fix,
and the operator reported successful processing of the four-file MP3/WAV/MP4/MXF
batch in 210.0 seconds. See [current validation](PHASE_10_VALIDATION.md). Existing
failed run history remains preserved; processing success does not imply a PASS
QC verdict or prove that the original source had no timestamp anomaly.
