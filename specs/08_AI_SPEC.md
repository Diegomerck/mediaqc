# 08 — Optional Local AI Specification

**Version:** 1.0.0

## 1. Principle

MediaQC is a deterministic QC product with optional local AI augmentation.

AI is not required for V1 core acceptance.

## 2. Modes

V1 enum:

```text
OFF
LOCAL
```

`LOCAL` may only be selectable if the engine reports compatible local capability/model installed.

There is no `CLOUD` mode in V1.

## 3. Allowed AI use cases

AI MAY:

- classify ambiguous visual anomaly evidence;
- generate concise human-readable explanations from structured measurements;
- prioritize review candidates;
- correlate multiple findings around the same timestamp;
- suggest likely intentional vs suspicious event classification;
- summarize a completed report locally.

## 4. Prohibited AI use cases

AI MUST NOT be the authority for:

- LUFS;
- true peak;
- sample peak;
- sample counts;
- frame rate;
- PTS/DTS;
- file/container metadata;
- clipping measurement;
- exact event timestamps when deterministic detectors provide them;
- overall PASS/WARN/FAIL override independent of profile rules.

## 5. Evidence-only grounding

AI input SHALL be constrained to:
- detector measurements;
- profile thresholds;
- evidence frames/images;
- limited local temporal context;
- metadata necessary for interpretation.

AI should not receive the whole source media unless a future spec explicitly defines such processing.

## 6. Structured AI output

Example:

```json
{
  "schema_version": "1.0.0",
  "finding_id": "uuid",
  "model_id": "local-model-id",
  "model_version": "version-or-hash",
  "classification": "LIKELY_INTENTIONAL_TRANSITION",
  "confidence": 0.78,
  "summary": "The luminance change coincides with a full-frame scene transition.",
  "recommended_action": "REVIEW",
  "evidence_refs": ["uuid1", "uuid2"]
}
```

Allowed `recommended_action`:
- `REVIEW`
- `LIKELY_VALID`
- `LIKELY_FALSE_POSITIVE`

The recommendation does not change finding disposition automatically.

## 7. Persistence

AI reviews SHALL be persisted separately from deterministic measurements.

If implementation adds an `ai_reviews` table, migration/spec update is required.

Minimum fields:
- finding ID;
- model ID/version/hash;
- prompt/template version;
- structured output;
- created timestamp.

## 8. Failure semantics

AI failure:
- logs warning;
- marks AI review unavailable;
- never fails deterministic analysis run;
- never deletes finding/evidence.

## 9. Hardware capability

CPU-only application remains valid.

Local AI may require:
- extra RAM;
- optional GPU;
- optional separately installed model pack.

Core installer MAY exclude large model weights.

If a model pack is separate, it must be installable offline from a local file.

## 10. Privacy

Local AI SHALL make no network request.

Any library with optional telemetry/download behavior must be configured to prevent automatic network access in offline mode.

## 11. Acceptance criteria

- App completes all required QC with AI OFF.
- Removing model files does not break core launch/analysis.
- AI output never mutates raw detector measurements.
- AI suggestions require explicit operator action to affect disposition.
