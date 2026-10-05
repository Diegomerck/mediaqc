# 06 — Desktop ↔ Engine IPC Specification

**Version:** 1.1.0

**Protocol version:** `1.0`

## 1. Transport

- stdin/stdout of the managed engine child process.
- UTF-8.
- One complete JSON object per line.
- Newline terminator: `\n`.
- No pretty-printed multi-line JSON on stdout.
- Engine stderr is diagnostics only.

## 2. Message envelopes

### Request

```json
{
  "type": "request",
  "protocol_version": "1.0",
  "request_id": "uuid",
  "method": "system.ping",
  "params": {}
}
```

### Successful response

```json
{
  "type": "response",
  "protocol_version": "1.0",
  "request_id": "uuid",
  "ok": true,
  "result": {}
}
```

### Error response

```json
{
  "type": "response",
  "protocol_version": "1.0",
  "request_id": "uuid",
  "ok": false,
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Human-readable message",
    "details": {}
  }
}
```

### Event

```json
{
  "type": "event",
  "protocol_version": "1.0",
  "event": "analysis.progress",
  "data": {}
}
```

## 3. Required methods

### `system.ping`

Params: `{}`

Result:

```json
{
  "pong": true
}
```

### `system.capabilities`

Result:

```json
{
  "engine_version": "0.1.0",
  "protocol_version": "1.0",
  "schema_version": 3,
  "platform": "windows",
  "ffmpeg": {
    "available": true,
    "version": "..."
  },
  "ffprobe": {
    "available": true,
    "version": "..."
  },
  "ai": {
    "local_available": false,
    "provider": null
  },
  "detectors": [
    {
      "id": "audio.clipping",
      "version": "1.0.0",
      "media_types": ["audio"],
      "requires_ai": false
    }
  ]
}
```

### `project.create`

Params:

```json
{
  "directory": "C:\\QC\\Episode104",
  "name": "Episode 104"
}
```

Result:
- project summary.

### `project.open`

Params:

```json
{
  "project_file": "C:\\QC\\Episode104\\project.sqlite"
}
```

Result:
- project summary.

### `project.get`

Returns project/media/run summaries.

### `media.inspect`

Params:

```json
{
  "project_id": "uuid",
  "absolute_path": "D:\\Media\\Episode104.mov"
}
```

Result:

```json
{
  "media_asset_id": "uuid",
  "inspection_status": "COMPLETED",
  "metadata": {},
  "streams": []
}
```

Long inspection MAY emit progress event.

### `profile.list`

Result: available profile summaries.

### `profile.get`

Params:
```json
{"profile_key": "general_technical_qc", "version": "1.0.0"}
```

### `profile.save_user_copy`

Validates and persists profile.

### `analysis.start`

Params:

```json
{
  "project_id": "uuid",
  "media_asset_id": "uuid",
  "profile_key": "general_technical_qc",
  "profile_version": "1.0.0",
  "ai_mode": "OFF"
}
```

Immediate result:

```json
{
  "analysis_run_id": "uuid",
  "status": "QUEUED"
}
```

### `analysis.cancel`

Params:
```json
{"analysis_run_id": "uuid"}
```

### `analysis.retry`

Creates a new run derived from previous run settings. Historical run remains.

### `analysis.get`

Returns:
- run status;
- summary;
- detector states;
- progress.

### `finding.list`

Params may include:
- run ID;
- severity;
- detector ID;
- disposition;
- time range.

### `finding.get`

Returns finding + evidence.

Phase 6 also returns persisted operator feedback in `feedback`, ordered by
creation: previous/new disposition, optional note, and UTC creation timestamp.
Finding lists include the same feedback for review after project reopen.

### `evidence.read`

Phase 6 bounded, read-only artifact retrieval. Params:

```json
{"evidence_id": "uuid"}
```

The engine resolves the saved reference in the open project's `evidence/`
directory; callers cannot supply filesystem paths. Evidence remains on disk.
One request reads at most 256 KiB of artifact content. PNG evidence returns
`data_url`, `start_time_seconds`, `end_time_seconds`, and `metadata`; metrics
JSON returns `text`. Image metadata includes the artifact SHA-256, finding
interval, and preview window length where applicable. Times use seconds.

The engine checks the saved run's source fingerprint and available artifact
digest before returning content. Missing, unreadable, unsupported, or oversized
artifacts return a structured `EVIDENCE_UNAVAILABLE` error. Changed artifacts
or changed source identity return `EVIDENCE_STALE`; source access errors retain
their existing media error codes. The UI must display these errors and retain
access to finding measurements. No regeneration or source modification occurs
in this method.

### `finding.set_disposition`

Params:

```json
{
  "finding_id": "uuid",
  "disposition": "FALSE_POSITIVE",
  "note": "Intentional black slate"
}
```

Returns the saved finding with evidence references and feedback. The optional
note is limited to 4,000 characters. In one transaction, append operator feedback,
save the disposition, and recalculate the overall result for a completed run.
`OPEN` and `CONFIRMED` findings contribute; `FALSE_POSITIVE` and `IGNORED` do
not, as specified by the product acceptance examples. Incomplete runs retain
a null overall result. The UI refreshes `analysis.get` after saving.

### `report.generate`

Params:

```json
{
  "analysis_run_id": "uuid",
  "format": "PDF"
}
```

Format enum:
- `HTML`
- `PDF`

Returns report path relative/absolute as appropriate.

### `settings.get`

### `settings.update`

Only documented settings may be changed.

### `system.shutdown`

Graceful engine shutdown.

## 4. Required events

### `engine.ready`

Emitted once protocol reader is ready.

### `analysis.status`

```json
{
  "analysis_run_id": "uuid",
  "status": "ANALYZING"
}
```

### `analysis.progress`

```json
{
  "analysis_run_id": "uuid",
  "overall_progress": 0.42,
  "stage": "ANALYZING",
  "current_detector_id": "video.freeze",
  "media_time_seconds": 812.42,
  "media_duration_seconds": 2852.1,
  "message": "Analyzing freeze candidates"
}
```

Progress values are advisory and SHALL be in `[0,1]`.

### `analysis.finding_created`

Contains compact finding summary.

### `analysis.detector_status`

Detector start/complete/fail.

### `analysis.completed`

Contains overall result and counts.

### `analysis.failed`

Contains error code/message.

### `analysis.cancelled`

Terminal cancellation event.

## 5. Error codes

Required baseline:

- `INVALID_REQUEST`
- `METHOD_NOT_FOUND`
- `PROTOCOL_VERSION_UNSUPPORTED`
- `PROJECT_NOT_FOUND`
- `PROJECT_INVALID`
- `MEDIA_NOT_FOUND`
- `MEDIA_CHANGED`
- `MEDIA_UNSUPPORTED`
- `MEDIA_INSPECTION_FAILED`
- `PROFILE_NOT_FOUND`
- `PROFILE_INVALID`
- `RUN_NOT_FOUND`
- `RUN_ALREADY_TERMINAL`
- `RUN_START_FAILED`
- `REPORT_FAILED`
- `ENGINE_INTERNAL_ERROR`

Details MAY contain nested machine-readable context.

## 6. Request correlation

Every request MUST have unique `request_id`.

Events are not responses and do not reuse request IDs as their only correlation mechanism; analysis events carry `analysis_run_id`.

## 7. Startup

Desktop:

1. spawn engine;
2. listen stdout/stderr;
3. wait for `engine.ready`;
4. call `system.capabilities`;
5. reject incompatible protocol.

If engine exits unexpectedly, UI displays recoverable engine error and allows restart.

## 8. Shutdown

Desktop sends `system.shutdown`, waits briefly for graceful exit, then terminates process if required.

Engine on shutdown:
- refuses new jobs;
- cancels/terminates active workers;
- closes DBs;
- emits/flushes final protocol where possible;
- exits.

## 9. Security

- no shell command strings;
- no eval;
- no arbitrary filesystem command IPC;
- validate all project/media paths;
- engine must not accept a request to modify arbitrary source files.

## 10. Acceptance criteria

- 10,000 sequential protocol messages parse without framing ambiguity.
- A file path containing spaces, Unicode, apostrophes, and `&` works.
- Debug logs never corrupt stdout JSON stream.
- Engine crash is surfaced to UI.
- Cancellation produces terminal event and no owned FFmpeg remains.

## 11. Phase 8 additive AI fields

`system.capabilities.ai` retains `local_available` and `provider` and adds nullable
`model_id`, `model_version`, and `reason`. The desktop may refresh capabilities
through the existing request envelope. No provider/model paths are accepted.
`analysis.start.ai_mode` accepts OFF or LOCAL. LOCAL capability controls UI
selection; an unavailable provider at execution time does not reject core QC.
`analysis.retry` preserves the saved mode. `analysis.get` includes saved `ai_mode`.

Finding responses may include `ai_review`: `id`, `finding_id`, nullable `model_id`
and `model_version`, `prompt_version`, `status` (COMPLETED or UNAVAILABLE), nullable
`error_code`, UTC `created_at`, and `output` (the AI schema object or null).
No row means not reviewed; LOCAL results must show this explicitly. OFF adds no
review object. Existing envelopes, deterministic fields, events and reports retain
their semantics. No AI-specific public command or settings persistence is added;
AI mode is selected per analysis and saved on the run.

## 12. Phase 10 additive batch contract

Protocol remains `1.0`; specification version 1.1.0 and schema version 3 are
independent. The capability example above is the Phase 10 target, not a claim that
the current engine implements it. Add this capability (absence means unavailable):

```json
{
  "batch": {
    "available": true,
    "contract_version": "1.0",
    "folder_extensions": [".wav", ".mp3", ".mp4", ".mxf"],
    "max_active_files": 1,
    "page_size": 50
  }
}
```

Validate request types, allowed keys, IDs, absolute paths, project membership,
state transitions, and page bounds. No filesystem command or source mutation is
exposed. Update engine dispatch and desktop allowlists only during implementation.

### Commands

| Method | Params | Result / behavior |
|---|---|---|
| `batch.create` | `project_id`, `name`, `source_kind` (FILE/FOLDER), `absolute_path`, optional `recursive` (false) | Immediate `{batch_id,status:IMPORTING,revision}`; asynchronous discovery. recursive=true is valid only for FOLDER. |
| `batch.list` | `project_id`, optional `limit` (50), `offset` (0) | `{batches,total,limit,offset}`; compact summaries, newest created first with ID tie-breaker. |
| `batch.get` | `batch_id` | Compact dashboard snapshot defined below. |
| `batch.items` | `batch_id`, optional `filter` (ALL), `limit` (50), `offset` (0) | `{batch_id,revision,items,total,limit,offset}`; total is matching row count. |
| `batch.start` | `batch_id`, `profile_key`, `profile_version`, `ai_mode` (OFF/LOCAL) | Persist exact profile/settings, then `{batch_id,status,revision}`. READY with candidates required. |
| `batch.pause` | `batch_id` | `{batch_id,status,revision}`; PAUSING or PAUSED, not a claim that the worker has stopped. |
| `batch.resume` | `batch_id` | `{batch_id,status,revision}`; accepts PAUSED or eligible INTERRUPTED. No replacement settings. |
| `batch.stop` | `batch_id` | Prompt `{batch_id,status,revision}` acknowledging STOPPING; terminal event follows cleanup. |
| `batch.retry` | `batch_id`, `selection` (ERROR/CANCELLED/UNATTEMPTED/ALL_UNSUCCESSFUL) | New batch with original-item links and saved settings; `{batch_id,status:IMPORTING,revision}`. |
| `batch.report.generate` | `batch_id`, `format` (HTML/PDF) | `{batch_report_id,batch_id,batch_revision,format,relative_path,absolute_path,generated_at}` after successful export. |

Page limits are integers 1–50, offsets nonnegative integers; responses must fit
existing transport limits. Names are 1–200 nonblank characters. Retry requires a
quiescent source batch with saved settings and eligible items. UNATTEMPTED selects
PENDING only in FAILED batches; ALL_UNSUCCESSFUL selects ERROR/CANCELLED plus those
eligible PENDING items. Retry recaptures identity for those paths, without rescanning
a folder, becomes READY, and still requires Run QC Analysis. Start for RETRY must
match inherited profile/AI settings and use the saved snapshot, even if installed
profile definitions changed. Original batches/runs are never reset or overwritten.

Start/Pause/Resume/Stop are idempotent in architecture-defined states; repeated
Start on RUNNING must match saved settings. Other invalid transitions leave DB
unchanged. create/retry always create new identity: after an uncertain timeout the
UI reconciles with batch.list instead of automatically repeating those commands.

### Compact snapshots and pages

`batch.get` returns:

- `batch_id`, `project_id`, `name`, `source_kind`, `source_path`, `recursive`,
  `status`, `revision`, `discovery_completed_at`, UTC lifecycle timestamps;
- `profile`: null before Start, otherwise `{profile_key,name,version}`; `ai_mode`;
- `counts`: `total`, `processed`, `pass`, `warn`, `fail`, `error`, `cancelled`,
  `processing`, `pending`, with architecture section 15 semantics;
- `import_summary`: `excluded`, `duplicate_encounters`, `directory_errors`,
  `complete` (discovery finished), `partial` (directory-access problems);
- `current`: null or `{item_id,analysis_run_id,file_name,relative_path,stage,
  file_progress,media_time_seconds,media_duration_seconds}`; unknown fields null;
- `overall_progress` (file-weighted fraction), `progress_estimated:true`,
  `can_continue_pending`, nullable `error_code`, `error_message`;
- `engine_session_id`, `progress_sequence` for live progress ordering.

batch.list entries contain batch/project IDs, name, status, revision, timestamps,
profile summary and counts, without per-file data. During IMPORTING counts are
provisional and overall QC progress remains 0.

`batch.items.filter` accepts ALL, NEEDS_ATTENTION, PASS, WARN, FAIL, ERROR,
CANCELLED, PROCESSING, PENDING, or IMPORT_RESULTS. ALL excludes EXCLUDED;
IMPORT_RESULTS includes EXCLUDED plus retained rows with duplicate_count > 0.
Filter in SQLite before paging. Processing rows sort by queue_position/id; import
rows by normalized path/id. During discovery use provisional normalized path/id order.

Each row contains `item_id`, `queue_position`, `file_name`, `relative_path`,
`absolute_path`, `status`, nullable `analysis_run_id`, nullable `overall_result`,
`issue_counts` (active INFO/WARN/FAIL for completed runs; null otherwise),
`error_code`, `error_message`, `exclusion_reason`, `duplicate_count`.
No detector arrays, probe/profile JSON, findings arrays, or evidence payloads.
Page total and revision use one DB snapshot; clamp unavailable pages after changes.

### Project and selected-file compatibility

project.create/open/get accept optional `summary_mode: "compact" | "full"`
(default full). Compact results include `id`, `name`, `project_file`, timestamps,
`media_asset_count`, `analysis_run_count`, `batch_count`; omit asset/run arrays and
do not stat every source. Preserve legacy full responses. The batch UI uses compact
mode from opening onward; historical standalone runs remain accessible through
`analysis.list` with `project_id`, optional `limit` (50), `offset` (0), returning
`{runs,total,limit,offset}` with run ID, asset ID, filename, status, overall_result,
profile name/version, and timestamps, newest first with ID tie-breaker. Maximum 50.

`analysis.get` may add `interpretation_notes: string[]`, derived from saved
stream metadata. Missing multichannel assignment and unknown grouping of multiple
audio streams qualify loudness as provisional/per-stream, not definitive program
compliance. Notes do not change measurements, findings, or verdicts.

Existing analysis.get/finding.list/finding.get/evidence.read serve the selected file
and finding with existing fields/safeguards. finding.list supports its existing
limit (default/max 100) and offset (default 0), returning findings and total.
Do not request every run or every finding for the dashboard. Single-run APIs remain
valid when not conflicting with scheduler ownership.

Finding responses may add `explanation: {summary,comparisons}`. Each comparison is
`{label,measured,unit,target,minimum,maximum,difference_from_limit}`; numeric fields
are finite numbers or null. Unit-aware adapters use saved finding thresholds or
the exact saved profile, never current settings. Difference is the nonnegative
distance outside the violated boundary, zero inside, null when inapplicable.
Unknown/categorical findings use saved prose and an empty comparisons array.
This is a derived read model, not stored detector output or an AI review.

### Events and errors

Add `batch.discovery`, `batch.status`, `batch.item_changed`, `batch.progress`,
`batch.completed`, `batch.stopped`, `batch.failed`, `batch.interrupted`. Each carries
`batch_id`, persisted `revision`, `engine_session_id`, and monotonic `sequence`
within that engine session. item_changed adds `item_id`, nullable `analysis_run_id`;
progress adds compact counts/current/overall_progress; discovery adds import_summary;
status/terminal events add status/error context. Existing analysis events are unchanged.

Events follow commits. Coalesce progress, never intentionally drop terminal state
notifications. The UI ignores stale session/sequence values, refreshes batch.get
and the visible page after persisted changes, and uses nonoverlapping compact
fallback polling while active. Reopen/event loss recovers from DB. Reset ordering
on engine restart. Disposition changes publish item_changed at the new revision.

Additional errors: BATCH_NOT_FOUND, BATCH_INVALID_STATE, BATCH_CONFLICT, BATCH_BUSY,
BATCH_EMPTY, BATCH_IMPORT_FAILED. Retain existing media/profile/project/report codes.
Messages include actionable structured context without source-media content.
Batch export accepts only PAUSED, COMPLETED, STOPPED, INTERRUPTED, or FAILED when
no other operation owns the scheduler. Reject conflicting report/start/resume
requests with BATCH_BUSY; report generation must not block active cancellation.


## Phase 12 explicit runtime audio applicability

analysis.start accepts optional audio_assignment (the explicit 0.1.0 source-bound contract object); all existing parameters remain required. The worker verifies full SHA-256 with cancellation before measurement. Invalid topology is INVALID_REQUEST; stale source fails MEDIA_CHANGED. analysis.get returns the saved assignment and applicability policy; retry preserves and revalidates that snapshot. Omission is legacy behavior, not an inferred channel expectation. Batch assignment editing and automatic assignment propagation are not added. Desktop assignment editing remains outside this minimal engine integration; callers may supply the documented stdio field.

Capabilities advertise schema_version 4 and audio_applicability with assignment_schema 0.1.0, policy_version explicit_audio_v1 and batch_assignments false. Optional parameters are backward-compatible with protocol 1.0.

Detailed HTML/PDF exports for assigned runs SHALL include the saved source SHA-256,
assignment identity, provenance, policy version, normalized channel expectations,
and ordered program members, including when no findings exist. Read only the saved
snapshot; omitted channels remain unknown. Export does not revalidate current media
or change historical runs/reports. Legacy unassigned runs have no fabricated intent.
