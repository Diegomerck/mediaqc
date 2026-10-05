# 05 — QC Profile Specification

**Version:** 1.0.0

## 1. Purpose

QC profiles define policy. Detector code defines measurement algorithms.

Profiles are versioned, serializable JSON documents.

YAML MAY be supported for developer-authored presets, but canonical runtime representation is JSON.

## 2. Canonical profile schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "mediaqc://schemas/qc-profile-1.0.0.json",
  "type": "object",
  "required": ["schema_version", "profile_key", "name", "version", "audio", "video"],
  "properties": {
    "schema_version": {"const": "1.0.0"},
    "profile_key": {"type": "string", "pattern": "^[a-z0-9_.-]+$"},
    "name": {"type": "string"},
    "version": {"type": "string"},
    "description": {"type": "string"},
    "audio": {"type": "object"},
    "video": {"type": "object"}
  }
}
```

## 3. Default built-in profile

V1 SHALL ship a conservative `general_technical_qc` profile.

It MUST NOT be branded as universal broadcaster compliance.

Example baseline:

```json
{
  "schema_version": "1.0.0",
  "profile_key": "general_technical_qc",
  "name": "General Technical QC",
  "version": "1.0.0",
  "description": "Conservative technical anomaly detection. Edit thresholds for delivery-specific requirements.",
  "audio": {
    "loudness": {
      "enabled": true,
      "integrated": {
        "enabled": true,
        "target_lufs": -23.0,
        "tolerance_lu": 1.0,
        "severity": "WARN"
      },
      "short_term": {
        "enabled": true,
        "max_lufs": null,
        "min_lufs": null,
        "min_event_duration_seconds": 1.0,
        "severity": "WARN"
      },
      "momentary": {
        "enabled": false,
        "max_lufs": null,
        "severity": "WARN"
      },
      "range": {
        "enabled": true,
        "min_lu": null,
        "max_lu": null,
        "severity": "WARN"
      }
    },
    "true_peak": {
      "enabled": true,
      "max_dbtp": -1.0,
      "severity": "FAIL"
    },
    "sample_peak": {
      "enabled": true,
      "max_dbfs": -0.1,
      "severity": "WARN"
    },
    "clipping": {
      "enabled": true,
      "near_full_scale_dbfs": -0.01,
      "min_consecutive_samples": 3,
      "merge_gap_ms": 5,
      "severity": "FAIL"
    },
    "silence": {
      "enabled": true,
      "threshold_dbfs": -60.0,
      "min_duration_seconds": 2.0,
      "ignore_head_seconds": 0.0,
      "ignore_tail_seconds": 0.0,
      "severity": "WARN"
    },
    "noise_floor": {
      "enabled": true,
      "quiet_percentile": 20.0,
      "max_estimated_noise_floor_dbfs": -45.0,
      "min_quiet_audio_seconds": 2.0,
      "severity": "WARN"
    },
    "hum": {
      "enabled": true,
      "fundamentals_hz": [50.0, 60.0],
      "harmonics": 5,
      "min_persistence_ratio": 0.25,
      "severity": "WARN"
    },
    "channel_imbalance": {
      "enabled": true,
      "max_difference_db": 6.0,
      "pairs": [[0, 1]],
      "severity": "WARN"
    },
    "phase_correlation": {
      "enabled": true,
      "pairs": [[0, 1]],
      "min_correlation": -0.25,
      "min_event_duration_seconds": 0.5,
      "severity": "WARN"
    },
    "dropout": {
      "enabled": true,
      "min_duration_ms": 5,
      "max_duration_ms": 250,
      "activity_threshold_dbfs": -35.0,
      "gap_threshold_dbfs": -65.0,
      "severity": "WARN"
    },
    "discontinuity": {
      "enabled": true,
      "sensitivity": 0.7,
      "severity": "WARN"
    }
  },
  "video": {
    "decode_integrity": {
      "enabled": true,
      "severity": "FAIL"
    },
    "frame_rate": {
      "enabled": true,
      "expected_fps": null,
      "tolerance_fps": 0.001,
      "severity": "WARN"
    },
    "timestamp_integrity": {
      "enabled": true,
      "max_interval_deviation_ratio": 0.25,
      "severity": "FAIL"
    },
    "black_frame": {
      "enabled": true,
      "max_mean_luma_normalized": 0.02,
      "min_black_pixel_ratio": 0.98,
      "min_duration_seconds": 0.5,
      "ignore_head_seconds": 0.0,
      "ignore_tail_seconds": 0.0,
      "severity": "WARN"
    },
    "near_black_frame": {
      "enabled": true,
      "max_mean_luma_normalized": 0.05,
      "min_duration_seconds": 1.0,
      "severity": "INFO"
    },
    "freeze": {
      "enabled": true,
      "min_duration_seconds": 0.5,
      "similarity_threshold": 0.995,
      "severity": "WARN"
    },
    "duplicate_frame": {
      "enabled": true,
      "similarity_threshold": 0.999,
      "min_repeat_count": 2,
      "severity": "INFO"
    },
    "frame_cadence": {
      "enabled": true,
      "severity": "WARN"
    },
    "luminance_anomaly": {
      "enabled": true,
      "sensitivity": 0.75,
      "severity": "WARN"
    },
    "flash": {
      "enabled": true,
      "min_luma_delta_normalized": 0.35,
      "max_duration_seconds": 0.25,
      "severity": "WARN"
    },
    "exposure_anomaly": {
      "enabled": true,
      "min_extreme_pixel_ratio": 0.98,
      "min_duration_seconds": 1.0,
      "severity": "INFO"
    },
    "color_anomaly": {
      "enabled": true,
      "sensitivity": 0.8,
      "severity": "INFO"
    },
    "visual_anomaly": {
      "enabled": true,
      "sensitivity": 0.85,
      "severity": "WARN"
    }
  }
}
```

The values above are V1 engineering defaults for development/testing, not claims of universal delivery compliance.

## 4. Null semantics

A null threshold means "do not evaluate this bound."

Example:

```json
"short_term": {
  "max_lufs": null
}
```

The detector may still calculate/store short-term metrics without producing a threshold finding.

## 5. Severity mapping

Each detector/profile section SHALL define the default severity for a threshold violation.

Future schema versions may support multiple threshold bands, for example WARN above -2 dBTP and FAIL above -1 dBTP. V1 MAY implement this only if required by a built-in profile.

## 6. Profile editor rules

UI SHALL validate:

- numeric ranges;
- min <= max;
- probabilities/sensitivity within [0,1] where applicable;
- channel indices non-negative;
- required values when detector enabled.

Saving edits to a built-in profile SHOULD create a user copy instead of mutating the built-in original.

## 7. Versioning

Profile identity:

```text
profile_key + version
```

Changing threshold values in a distributed built-in profile requires version bump.

Historical runs retain snapshot, so user-created profiles may be edited while preserving old run context.

## 8. Import/export

V1 SHOULD support profile JSON export/import if time permits.

Imported profiles MUST be schema-validated before persistence.

## 9. Acceptance criteria

- No detector policy threshold is required from hard-coded detector values.
- A run stores full profile snapshot.
- Invalid profiles cannot start a run.
- Disabling a detector prevents its execution.
- Editing a built-in profile does not silently rewrite historical results.


## 10. Phase 12 audio applicability design boundary

The developer contract in `docs/PHASE_12_AUDIO_APPLICABILITY_CONTRACT.md`
defines explicit source-bound channel expectations and ordered program members.
Its 0.1.0 prototype does not modify this profile schema or runtime verdicts.
Role, measurement scope, compliance and confirmed technical defect remain separate.
Any future runtime applicability policy must be explicitly versioned; it must not
reinterpret saved multitrack/mono-leg measurements as designated stereo programs
or silently remove active findings from historical results.


## Phase 12 explicit runtime audio applicability

The opt-in runtime policy explicit_audio_v1 is separate from unchanged General Technical QC 1.2.0 thresholds. It evaluates silence for explicitly expected channels, retains unused and unknown silence as INFO, and evaluates program loudness only on declared programs. Unknown scope never asserts technical cleanliness; analysis/report interpretation notes explain unresolved coverage. Raw measurement, original threshold severity, assignment identity and applicability remain retained. Canonical severity/disposition aggregation is unchanged. This policy applies only to new assigned runs, not historical results.

The new applicability severities reside in the versioned `qc/audio_applicability_v1.json` policy document, not detector constants. Changing its distributed semantics requires a new policy version; saved findings retain their actual severity and evaluation metadata.
