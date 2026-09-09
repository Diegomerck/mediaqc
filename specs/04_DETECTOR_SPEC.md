# 04 — Detector and Finding Specification

**Version:** 1.0.0

## 1. Canonical detector interface

Conceptual Python interface:

```python
from dataclasses import dataclass
from typing import Protocol, Sequence

class Detector(Protocol):
    detector_id: str
    detector_version: str

    def supports(self, context: "DetectorContext") -> bool: ...

    def analyze(
        self,
        context: "DetectorContext",
    ) -> Sequence["FindingDraft"]: ...
```

`DetectorContext` SHALL provide, without exposing UI concerns:

```python
@dataclass(frozen=True)
class DetectorContext:
    analysis_run_id: str
    media_asset: "MediaAsset"
    streams: tuple["MediaStream", ...]
    qc_profile: "QcProfileSnapshot"
    work_dir: str
    cancellation: "CancellationToken"
    media_tools: "MediaTools"
    logger: "StructuredLogger"
```

Detectors SHALL not write directly to SQLite. Orchestration persists returned results.

## 2. Finding JSON schema

Canonical transport/persistence representation:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "mediaqc://schemas/finding-1.0.0.json",
  "type": "object",
  "required": [
    "id",
    "detector_id",
    "detector_version",
    "severity",
    "title",
    "description",
    "measurements",
    "disposition"
  ],
  "properties": {
    "id": {"type": "string", "minLength": 1},
    "detector_id": {"type": "string", "minLength": 1},
    "detector_version": {"type": "string", "minLength": 1},
    "stream_id": {"type": ["string", "null"]},
    "severity": {"enum": ["INFO", "WARN", "FAIL"]},
    "confidence": {
      "type": ["number", "null"],
      "minimum": 0.0,
      "maximum": 1.0
    },
    "start_time_seconds": {"type": ["number", "null"], "minimum": 0},
    "end_time_seconds": {"type": ["number", "null"], "minimum": 0},
    "duration_seconds": {"type": ["number", "null"], "minimum": 0},
    "title": {"type": "string"},
    "description": {"type": "string"},
    "measurements": {"type": "object"},
    "threshold": {"type": ["object", "null"]},
    "evidence": {
      "type": "array",
      "items": {"$ref": "mediaqc://schemas/evidence-ref-1.0.0.json"}
    },
    "metadata": {"type": "object"},
    "disposition": {
      "enum": ["OPEN", "CONFIRMED", "FALSE_POSITIVE", "IGNORED"]
    }
  }
}
```

If start/end exist:

```text
end_time_seconds >= start_time_seconds
duration_seconds ~= end - start
```

Tolerance is permitted for stream/time-base rounding.

## 3. Evidence types

Canonical V1 values:

- `AUDIO_WAVEFORM`
- `AUDIO_SPECTROGRAM`
- `AUDIO_CLIP_METADATA`
- `VIDEO_FRAME`
- `VIDEO_FRAME_BEFORE`
- `VIDEO_FRAME_AFTER`
- `VIDEO_CONTACT_SHEET`
- `METRICS_JSON`
- `FFMPEG_LOG`

Evidence content stays on disk; finding carries references.

## 4. Detector result contract

A detector invocation yields:

```python
@dataclass
class DetectorResult:
    findings: list[FindingDraft]
    metrics: dict
    warnings: list["DetectorWarning"]
```

Exceptions should be reserved for failed detector execution.

## 5. Canonical audio detector definitions

### `audio.loudness.integrated`

Purpose: integrated programme loudness measurement.

Output metrics:
- `integrated_lufs`
- optional `target_lufs`
- optional `deviation_lu`

Finding behavior:
- no issue if within profile target tolerance;
- WARN/FAIL according to profile.

This is a whole-stream/program metric and may have null timeline.

### `audio.loudness.short_term`

Measure short-term loudness over compliant/defined windows.

Finding:
- create event(s) when configured max/min bounds are exceeded for required duration.

Metrics:
- `short_term_lufs`
- `limit_lufs`
- `window_seconds`

### `audio.loudness.momentary`

Similar to short-term, using momentary window.

### `audio.loudness.range`

Whole-program LRA metric.

### `audio.true_peak`

Metrics:
- `true_peak_dbtp`
- per-channel peaks if available.

### `audio.sample_peak`

Metrics:
- `sample_peak_dbfs`
- channel.

### `audio.clipping`

Candidate definition:
- samples at/above configured near-full-scale threshold;
- group neighboring clipped samples into events by profile gap tolerance.

Metrics:
- `sample_peak_dbfs`
- `clipped_sample_count`
- `channel_indices`
- `max_consecutive_samples`

V1 SHALL avoid equating high sample peak with confirmed audible distortion; report clipping evidence.

### `audio.silence`

Detect periods below configured threshold for configured minimum duration.

Do not call all silence an error. Profile determines whether it is INFO/WARN/FAIL and may define edge exemptions.

Metrics:
- `rms_dbfs`
- `threshold_dbfs`
- `duration_seconds`

### `audio.noise_floor`

V1 algorithm requirement:

1. process audio in short overlapping windows;
2. compute RMS/energy and spectral features;
3. select likely quiet windows using profile percentile/gating configuration;
4. estimate broadband floor;
5. return confidence based on amount/stability of quiet evidence;
6. optionally exclude exact digital silence.

Metrics:
- `estimated_noise_floor_dbfs`
- `quiet_window_count`
- `quiet_audio_seconds`
- `confidence_basis`

A detector MUST NOT claim a meaningful noise-floor estimate when insufficient quiet material exists. It should return a warning/metric state such as `INSUFFICIENT_QUIET_REGIONS`.

### `audio.hum`

Analyze spectral energy near:
- 50 Hz family;
- 60 Hz family;
- configured harmonics.

Metrics:
- `fundamental_hz`
- `hum_level_db_relative`
- `harmonics_detected`
- `persistence_ratio`

### `audio.channel_imbalance`

For multi-channel audio, compare profile-selected channel pairs/groups.

Metrics:
- channel RMS/loudness values;
- difference in dB.

Do not assume every multichannel layout should be balanced; profile defines applicable channel pairs.

### `audio.phase_correlation`

Compute normalized channel correlation for profile-selected stereo pair(s).

Metrics:
- `correlation_coefficient`
- `window_seconds`
- affected duration.

Thresholds profile-defined.

### `audio.dropout`

Detect abrupt short energy gaps inside otherwise active signal.

Required signals:
- pre-gap activity;
- gap energy;
- post-gap activity;
- duration;
- optional spectral continuity context.

Must distinguish sustained intentional silence from short dropout candidate.

### `audio.discontinuity`

Detect abrupt waveform/spectral discontinuity not necessarily silent.

May combine:
- derivative/jump statistics;
- spectral flux;
- repeated micro-segments;
- context windows.

This is confidence-scored and SHOULD default WARN rather than FAIL until tuned.

## 6. Canonical video detector definitions

### `video.decode_integrity`

Capture:
- FFmpeg decode errors;
- corrupt packets/frames where exposed;
- unexpected termination.

This is deterministic.

### `video.frame_rate`

Compare declared/average/real frame-rate values and profile expectations.

Do not flag variable frame rate merely because `avg_frame_rate` differs from `r_frame_rate`; evaluate timestamp behavior.

### `video.timestamp_integrity`

Analyze decoded packet/frame timestamps.

Detect:
- missing PTS where required;
- non-monotonic timestamps;
- duplicate timestamps;
- abnormal frame intervals;
- negative timestamps when profile forbids them.

### `video.black_frame`

Candidate using luminance statistics.

Required metrics:
- `mean_luma_normalized`;
- `black_pixel_ratio`;
- duration.

Context/profile handles minimum duration and edge exemptions.

### `video.near_black_frame`

Similar, with higher luma threshold than pure black.

### `video.freeze`

V1 algorithm SHOULD combine:
- downscaled frame difference;
- perceptual/hash similarity;
- consecutive duration;
- motion before/after.

Finding created only after minimum freeze duration.

Store:
- start;
- end;
- duration;
- similarity statistic;
- surrounding motion statistic.

### `video.duplicate_frame`

Detect identical/near-identical adjacent frames/sequences.

Do not automatically classify legitimate static shots as duplicate-frame faults. Detector can provide candidate findings and profile may require cadence evidence.

### `video.frame_cadence`

Analyze repeated-frame pattern and timestamp intervals for suspicious cadence.

Examples:
- isolated unintended repeats;
- periodic repeat patterns inconsistent with expected cadence.

### `video.luminance_anomaly`

Detect statistically unusual sudden luma changes using neighboring context.

### `video.flash`

Candidate requires a short-duration large change followed by return or other profile-defined transient behavior.

This avoids treating every scene cut as a flash.

### `video.exposure_anomaly`

Conservative detection of sustained extreme clipping/crushing using luma histogram ratios.

Does not judge creative exposure.

### `video.color_anomaly`

Conservative detection of severe channel/color distribution anomalies.

Does not perform grading judgement.

### `video.visual_anomaly`

Generic candidate detector combining signals such as:
- frame difference;
- histogram divergence;
- edge-density discontinuity;
- blockiness/corruption heuristics.

Default severity SHOULD be WARN/INFO unless profile explicitly promotes it.

## 7. Confidence

Use confidence only for probabilistic/heuristic detections.

Deterministic threshold violations MAY use `1.0` or null according to implementation policy, but be consistent.

Confidence MUST NOT replace measurements.

## 8. Finding grouping

Detectors SHOULD merge contiguous windows into one event using profile-defined or detector-documented gap tolerance.

Avoid one finding per frame/sample when a single event is appropriate.

## 9. Detector registry

Engine SHALL expose:

```json
{
  "detectors": [
    {
      "id": "video.freeze",
      "version": "1.0.0",
      "media_types": ["video"],
      "requires_ai": false
    }
  ]
}
```

## 10. Acceptance criteria

- All canonical IDs are stable.
- All detector outputs validate against finding schema.
- Threshold policy comes from selected profile.
- Timeline units are seconds.
- Synthetic injected defect timestamps are detected within testing tolerances.
- Heuristic detectors expose confidence and evidence.
