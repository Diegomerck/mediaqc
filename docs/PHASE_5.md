# Phase 5 — deterministic video QC

Phase 5 adds all 13 canonical video IDs to the existing sequential job registry.
Audio algorithms, JSON-lines IPC, SQLite schema, process ownership, recovery and
source-file handling remain in place. Shared stream finding construction was
extracted from the audio base; audio imports retain their existing interface.
Authoritative specifications are unchanged.

## Measurement pipeline

Bundled ffprobe streams original decoded frame PTS and durations to a JSONL cache.
Bundled FFmpeg then decodes the selected stream with passthrough frame sync to
bounded RGB24 frames. Both passes use `MediaTools.stream` and its existing process
registry, cancellation and bounded stderr drainer. Errors are detected even when
the tool exits zero after recovering from corrupt packets. A complete cache marker
is written only after both passes finish; cancellation never publishes one.
Decode failure retains its stderr excerpt and a structured integrity finding;
dependent detectors fail explicitly rather than present incomplete measurements
as a clean result. A declared stream duration longer than the decoded timeline by
the profile tolerance is also reported as incomplete.

MP4 and MXF use this same demux/decode path, with no extension allowlist or OpenCV
container reader. Supported contained codecs depend on the bundled FFmpeg build.
Every video stream is mapped explicitly. Every decoded frame is processed; there
is no temporal subsampling. Spatial measurement dimensions are profile settings,
defaulting to 320 × 180, including for 4K input. Width/height must be integers from
16 to 1920. Only current/previous images and constant-size event state stay in RAM.
JSONL disk usage grows with frame count; findings grow with detected event count,
as in Phase 4. Cache files are retained under `cache/<run-id>/` and contain numbers,
not decoded media or copies of the source.

OpenCV headless 4.13.0.92 is pinned and bundled. Image features use RGB frame
difference, BT.709 weighted normalized luma, 32-bin luma histogram divergence,
9 × 8 difference-hash similarity and Sobel edge density. Feature extraction
constants are algorithmic; all decision gates and severities live in the profile.
RGB conversion uses FFmpeg's decoded color conversion. These measurements are
normalized code-value heuristics, without HDR tone mapping, grading judgement,
absolute display luminance or broadcast compliance claims. Spatial downscaling
can reduce sensitivity to small localized defects.

## Detectors and policy

- Decode integrity: recovered/unrecovered decode errors, missing frames between
  passes, zero-frame decodes and incomplete declared duration; default FAIL.
- Frame rate: declared average/real and observed rate metrics, comparison against
  an optional expected FPS, and disagreement with a constant decoded cadence.
  Different declared rates alone do not classify VFR as a defect.
- Timestamp integrity: missing PTS, negative PTS if forbidden, duplicate and
  decreasing PTS, excessive gaps, and interval deviation when CFR is required.
  `allow_variable_frame_rate` defaults true; `max_gap_seconds` defaults 0.5.
  Original signed PTS is retained in measurements; canonical finding times are
  non-negative. Missing PTS uses an explicitly inferable display timeline only;
  original PTS stays null and the required-PTS check still fails.
- Black/near-black: mean luma and pixel-ratio gates, minimum duration and head/tail
  exemptions. A range touching an exempt interval is exempted as a whole.
- Freeze: frame difference plus hash similarity, minimum duration and motion on
  both sides. Three consecutive moving frames are required by default, avoiding
  static shots bracketed by cuts. Head/tail freezes without both contexts are
  conservatively suppressed unless motion-context policy is disabled.
- Duplicate/cadence: adjacent similarity, minimum repeated-frame count, maximum
  repeat duration and surrounding motion. Cadence reports isolated short repeated
  sequences in motion, including recurring instances, without claiming knowledge
  of editorial intent. Static long shots are suppressed.
- Luminance/flash: sufficiently large luma excursion followed by a return within
  the profile maximum duration and return tolerance. Sustained cuts do not qualify.
- Exposure: sustained extreme shadow or highlight pixel ratio; default INFO.
- Color: sustained severe channel spread and dominant-pixel ratio; default INFO.
- Visual anomaly: conjunction of difference, histogram and edge-discontinuity
  gates, followed by return of luma and edge density. Default WARN candidate.

Event duration boundaries include exact minimum/maximum values (1 ns numerical
rounding allowance). Contiguous threshold/repeated frames form events. Heuristic
findings include their raw features and a fixed uncalibrated candidate confidence
of 0.8; confidence is not a replacement for measurements or policy.

`general_technical_qc` 1.2.0 adds explicit video gates and measurement settings.
The original 1.0.0 and 1.1.0 documents remain available unchanged. Retries retain
historical snapshots; added gates absent from old snapshots resolve against the
current distributed defaults, and effective detector policy is saved in findings.
Validation covers ranges, dimensions, counts, booleans, finite values, inverted
bounds and positive expected rates. Disabled detectors are not scheduled.

## Persistence and UI

The job manager persists video findings and `METRICS_JSON` evidence under
`evidence/video/<run-id>/`. Evidence write failures remain explicit in finding
metadata. Existing finding IPC and pagination, detector metrics, counts, severity
aggregation, progress, cancellation, retry and reopen behavior apply to video.
The existing results component displays audio/video measurements and evidence
paths. The new-analysis text includes video; the profile picker offers 1.2.0.

No timeline, rendered stills/contact sheets, waveform viewer, disposition editor,
report generation, AI or Phase 6+ features were added.

## Validation

`npm run fixtures:video` generates the manifest corpus, including reproducible
compressed-packet corruption. Synthetic event expectations use 50 ms tolerance
(25 fps fixtures), unchanged when correcting detector failures. Clean controls
include motion, static shots, hard cuts and fades. Additional tests cover boundary
values, static shots between cuts, missing/duplicate/decreasing/negative timestamps,
VFR, MP4/MXF, cache reuse, source hashes/mtime, persisted evidence/reopen, failures,
real child cancellation, disabled detectors and bounded long-sequence event state.

`npm run check` retains every previous gate and adds `phase5:smoke` (22 gates).
It builds the Windows Tauri release and packaged engine. The Phase 5 native
controller smoke analyzes MP4 and MXF with empty end-user PATH/PYTHONPATH and
checks findings/timing, persisted evidence, restart, cancel/retry and immutable
source bytes/mtime. Empty PATH demonstrates bundled dependencies; it is not a
claim of testing with a network firewall or on a clean installation.

Recorded clean-video validation was completed on 2026-09-18 using four external,
owner-reviewed UHD 10-bit 4:2:2 MXF files (195.028167 seconds total). All 52 video
detector executions completed with zero video findings, satisfying the specified
observed false-positive budget on this corpus. Full-file SHA-256, size and mtime
checks confirmed unchanged sources. See [recorded corpus validation](PHASE_5_CLEAN_CORPUS.md)
for exact criteria, metadata, retained audio findings, hashes and reproducibility.
This short corpus does not establish statistical assurance for other content.
The normal full-profile runs retained audio policy FAIL results; those do not
represent video false positives. No code or threshold changes were needed.
Clean-machine/installer validation remains Phase 9.
