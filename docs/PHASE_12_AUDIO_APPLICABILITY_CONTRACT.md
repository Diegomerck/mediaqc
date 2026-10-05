# Phase 12 program/channel applicability contract

Status: developer contract **0.1.0**, defined and executable for review. This is
not wired into production IPC, persistence, detector scheduling or verdicts.
General Technical QC 1.2.0 and silence algorithm 1.0.1 remain unchanged. No
reference filename or measured level determines an assignment.

## Three separate records

1. **Measurement evidence:** detector/version, measured value or explicit failure/
   insufficient-data state, units, actual stream/channel/program scope, timeline,
   source identity and tool provenance. Roles never erase or rewrite these facts.
2. **Applicability/compliance evaluation:** references the measurement, assignment
   snapshot and profile/policy version; records scope eligibility separately from
   threshold comparison. A valid measurement on the wrong scope is not a program
   compliance result. Missing scope/coverage is unresolved, never measured-clean.
3. **Technical review:** confirmed defect, expected content, or unresolved intent,
   with review provenance. A policy exceedance is not itself confirmed damage.
   Existing finding severity/disposition enums and historical verdicts remain intact.

These are conceptual records for a future integration, not added finding fields
or newly persisted tables in this step.

## Source-bound assignment schema

The executable parser is `tools/audio_applicability_contract.py`. Every root and
nested object rejects unknown fields. Example for a synthetic seven-channel file:

```json
{
  "schema_version": "0.1.0",
  "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "provenance": "owner-review:assignment-001",
  "channels": [
    { "member": [0, 0], "role": "mix", "expectation": "expected" },
    { "member": [0, 1], "role": "mix", "expectation": "expected" },
    { "member": [0, 2], "role": "iso", "expectation": "expected" }
  ],
  "programs": [
    {
      "program_id": "production",
      "layout": "stereo",
      "members": [
        [0, 0],
        [0, 1]
      ]
    }
  ]
}
```

The fingerprint above is a placeholder; the parser requires equality with the
independently supplied full source SHA-256. A production implementation must bind
this to its verified source/run identity rather than trusting an imported claim.
No source access or hashing is performed by the parser itself.

- A member is `[absolute_ffprobe_stream_index, zero_based_channel_index]`, not an
  audio-stream ordinal or a one-based operator label. Both integers are validated
  against the caller's probed audio-only inventory; booleans are rejected.
- `role` is `mix`, `iso`, `other` or `unknown`. It describes the signal's purpose,
  not whether silence is allowed. An ISO is not automatically unused.
- `expectation` is `expected`, `unused` or `unknown` for the whole asset. Expected
  audio means evaluate applicable silence policy; it does not mean continuous
  sound or that every quiet dialogue interval is a technical fault. Unused means
  explicitly declared unnecessary for this source, not inferred from low energy.
- Omitted channels resolve to `unknown/unknown`. No default silence exemption.
  An ambiguous `optional` flag is deliberately not supported: its silence policy
  would need an explicit meaning before it could affect a result.
- Assignments must be unique per channel. Program IDs must be unique and nonempty.
  Mono has one member; stereo has two ordered members, Left then Right. No duplicate
  member within a program; reuse across independently named programs is allowed.
  Every program member must explicitly expect audio. ISO members can form an
  explicitly selected program; role alone does not select or reject a program.
- Only mono and stereo are defined in 0.1.0. No inferred surround order, summing,
  downmix, gain, normalization, resampling, offset correction or temporal exemption
  is represented. Unsupported requests fail validation, not automatic conversion.
- Provenance is a nonempty local review/import reference. Parsed snapshots are
  deeply immutable tuples/frozen records. Their identity hashes the canonical
  document and validated audio inventory; changing program order or expectations
  makes a new snapshot. Arrays retain declared order; equivalent reordered
  documents may receive different identities, which is safe for audit purposes.

## Measurement scope and eligibility

A future measurement scope must identify `channel`, `stream` or `program`, the
ordered physical members, program/layout if relevant, and the assignment identity
used for program measurement. Channel measurements do not require an assignment
but must record exact physical scope. A new assignment may reference retained
raw evidence in a new evaluation; it must not rewrite the original evaluation.
A mono leg or aggregate multitrack measurement cannot be relabelled as a stereo
program measurement. Recompute with the explicitly selected members.

| Evidence / expectation                                  | Applicability result        | Consequence                                                                        |
| ------------------------------------------------------- | --------------------------- | ---------------------------------------------------------------------------------- |
| Exact channel, `expected`                               | `APPLICABLE`                | Evaluate selected silence thresholds; retain candidate for review.                 |
| Exact channel, `unused`                                 | `EXPECTED_UNUSED`           | Silence is expected for this channel; preserve measurement and legacy raw finding. |
| Exact channel, unknown/omitted expectation              | `UNRESOLVED`                | Do not infer clean or defective from role or level.                                |
| Aggregate stream with mixed channel expectations        | Scope insufficient          | Never blanket-exempt the stream; obtain per-channel evidence.                      |
| Missing/failed/insufficient measurement                 | Not evaluated               | No passing compliance or clean technical conclusion.                               |
| Explicit program with matching measured scope           | Eligible for program policy | Compare measured program loudness to selected profile limits.                      |
| Mono-leg/aggregate evidence presented as stereo program | Scope mismatch              | Retain evidence; do not evaluate as the designated program.                        |

The executable `silence_applicability` helper returns only the first three scope
labels. It accepts an exact channel member, no waveform, measurement, threshold,
finding or verdict; it cannot establish measurement success or suppress a finding.
The broader table is the integration contract, not a claim that all rows are
implemented by this prototype.

No assignment suppresses decode integrity, discontinuity, clipping or peak
measurements. Peaks still require precise channel/program scope; exceeding a
configured limit remains a compliance fact rather than proof of audible distortion.
For unused-channel non-silence events, retain the event and review it independently;
`unused` is not a general technical-error waiver.

Cross-stream program measurement requires verified compatible sample clocks,
timeline alignment and coverage. Validate actual decoded timing, not merely two
matching channel counts. Missing legs, gaps, differing starts/ends or unsupported
rates are unresolved/unsupported until an explicit routing policy handles them.
Never pad, trim, shift, sum, or resample silently. These routing checks are future
integration requirements; this parser validates topology only. Prior synthetic
L/R routing tests establish matching-timing cases, not arbitrary synchronization.

## Consequences for production multitracks

The supplied WAV roles identify stream 0 channels 0/1 as L/R and 2-6 as lavaliers.
The supplied MXF roles identify streams 1/2 channel 0 as L/R and streams 3-8
channel 0 as unused ISO positions for this reference. These are assignment data,
not format/name rules. Other MXF ISOs can explicitly expect audio and must be
checked. A lavalier role alone does not specify allowed quiet intervals; record
unknown expectations where that detail has not been reviewed. The tests use
explicitly expected synthetic WAV ISOs to exercise the required-audio case.

Current silence 1.0.1 uses stream RMS for event detection. Two active mix channels
can conceal silence on five required ISOs within a seven-channel WAV. Its retained
channel RMS metrics establish measurement evidence but lack per-channel timed
silence events. A characterization regression records this gap; its passing test
is not evidence that required-channel silence acceptance is satisfied.

A future implementation must maintain bounded per-channel silence regions in the
existing streaming pass, preserving the zero-tail fix and policy thresholds. It
needs positive required-channel silence, expected-unused, mixed-role, timing,
missing-leg and cancellation/cache parity gates before promotion. No such detector
change is made here because this step defines the contract rather than changing
scope and resulting findings implicitly.

## Smallest explicit production integration

Before runtime use, amend the applicable schemas and specify a versioned
applicability policy binding separately from General Technical QC 1.2.0. Current
verdict aggregation counts active WARN/FAIL findings; the new scope label cannot
silently remove an existing warning or mark it ignored/false-positive. Legacy
runs and reports must continue using their saved inputs/results.

Implement immutable per-run assignment headers plus relational channel/program/
ordered-member rows, referencing the existing run and stream identities. Preserve
provenance and a serialized audit representation without hiding core query fields
solely in JSON. UI supplies explicit assignments; engine validates them; stdio IPC
transports versioned data. Batch assignments resolve against each asset's inventory
and identity, never blindly reuse indices across unlike files. A changed source or
edited assignment requires revalidation and a new run/evaluation, not history edits.

Scope-aware measurements and separate applicability evaluations must then feed
new reports/UI with explicit unresolved coverage. A versioned policy must state
whether and how expected-unused silence affects new-run verdicts. It must retain
unexpected silence on required mix/ISO members, and never treat missing or failed
measurement as a pass. No database migration, IPC/UI implementation, new profile,
automatic finding disposition or verdict-policy change is included in this step.

## Runtime integration checkpoint

The [runtime audio increment](PHASE_12_AUDIO_RUNTIME.md) supersedes earlier
developer-only implementation-status statements. Explicit single-file assignments
now activate runtime channel silence and program loudness applicability; historical
results and unassigned-run behavior are preserved. See that report for remaining
discontinuity failures, validation and UI/batch limitations.
