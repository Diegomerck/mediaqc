# 06 — Desktop ↔ Engine IPC Specification

**Version:** 1.0.0  
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
  "schema_version": 1,
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

### `finding.set_disposition`

Params:

```json
{
  "finding_id": "uuid",
  "disposition": "FALSE_POSITIVE",
  "note": "Intentional black slate"
}
```

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
