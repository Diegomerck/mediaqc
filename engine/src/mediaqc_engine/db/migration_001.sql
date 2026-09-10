CREATE TABLE schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    app_version_created TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE media_assets (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    absolute_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    modified_at TEXT,
    duration_seconds REAL,
    container_format TEXT,
    fast_fingerprint_sha256 TEXT,
    inspection_status TEXT NOT NULL,
    inspection_error_code TEXT,
    inspection_error_message TEXT,
    ffprobe_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_media_assets_project ON media_assets(project_id);

CREATE TABLE media_streams (
    id TEXT PRIMARY KEY,
    media_asset_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
    stream_index INTEGER NOT NULL,
    stream_type TEXT NOT NULL,
    codec_name TEXT,
    codec_long_name TEXT,
    duration_seconds REAL,
    time_base TEXT,
    start_time_seconds REAL,
    language TEXT,
    disposition_json TEXT,
    width INTEGER,
    height INTEGER,
    pixel_format TEXT,
    color_space TEXT,
    color_transfer TEXT,
    color_primaries TEXT,
    field_order TEXT,
    avg_frame_rate TEXT,
    real_frame_rate TEXT,
    sample_rate_hz INTEGER,
    channel_count INTEGER,
    channel_layout TEXT,
    sample_format TEXT,
    bit_rate INTEGER,
    metadata_json TEXT,
    UNIQUE(media_asset_id, stream_index)
);

CREATE INDEX idx_media_streams_asset ON media_streams(media_asset_id);

CREATE TABLE qc_profiles (
    id TEXT PRIMARY KEY,
    profile_key TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT,
    profile_json TEXT NOT NULL,
    is_builtin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(profile_key, version)
);

CREATE TABLE analysis_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    media_asset_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
    qc_profile_id TEXT REFERENCES qc_profiles(id),
    qc_profile_snapshot_json TEXT NOT NULL,
    status TEXT NOT NULL,
    overall_result TEXT,
    engine_version TEXT NOT NULL,
    protocol_version TEXT NOT NULL,
    ffmpeg_version TEXT,
    ffprobe_version TEXT,
    media_fingerprint_sha256 TEXT,
    ai_mode TEXT NOT NULL DEFAULT 'OFF',
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    error_code TEXT,
    error_message TEXT
);

CREATE INDEX idx_runs_project ON analysis_runs(project_id);
CREATE INDEX idx_runs_asset ON analysis_runs(media_asset_id);
CREATE INDEX idx_runs_status ON analysis_runs(status);

CREATE TABLE detector_executions (
    id TEXT PRIMARY KEY,
    analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    detector_id TEXT NOT NULL,
    detector_version TEXT NOT NULL,
    stream_id TEXT REFERENCES media_streams(id),
    status TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    progress REAL,
    error_code TEXT,
    error_message TEXT,
    metrics_json TEXT
);

CREATE INDEX idx_detector_exec_run ON detector_executions(analysis_run_id);

CREATE TABLE findings (
    id TEXT PRIMARY KEY,
    analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    detector_execution_id TEXT REFERENCES detector_executions(id) ON DELETE SET NULL,
    detector_id TEXT NOT NULL,
    detector_version TEXT NOT NULL,
    stream_id TEXT REFERENCES media_streams(id),
    severity TEXT NOT NULL,
    confidence REAL,
    start_time_seconds REAL,
    end_time_seconds REAL,
    duration_seconds REAL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    measurements_json TEXT NOT NULL,
    threshold_json TEXT,
    metadata_json TEXT,
    disposition TEXT NOT NULL DEFAULT 'OPEN',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_findings_run ON findings(analysis_run_id);
CREATE INDEX idx_findings_severity ON findings(analysis_run_id, severity);
CREATE INDEX idx_findings_time ON findings(analysis_run_id, start_time_seconds);
CREATE INDEX idx_findings_detector ON findings(analysis_run_id, detector_id);

CREATE TABLE evidence (
    id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    evidence_type TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    mime_type TEXT,
    start_time_seconds REAL,
    end_time_seconds REAL,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_evidence_finding ON evidence(finding_id);

CREATE TABLE operator_feedback (
    id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    previous_disposition TEXT NOT NULL,
    new_disposition TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_feedback_finding ON operator_feedback(finding_id);

CREATE TABLE reports (
    id TEXT PRIMARY KEY,
    analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    report_type TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    generator_version TEXT NOT NULL,
    options_json TEXT
);

CREATE INDEX idx_reports_run ON reports(analysis_run_id);

CREATE TABLE application_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
