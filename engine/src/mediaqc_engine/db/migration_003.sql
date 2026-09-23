CREATE TABLE batches (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    name TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('FILE','FOLDER','RETRY')),
    source_path TEXT,
    recursive INTEGER NOT NULL DEFAULT 0 CHECK (recursive IN (0,1)),
    original_batch_id TEXT REFERENCES batches(id),
    status TEXT NOT NULL CHECK (status IN
        ('IMPORTING','READY','RUNNING','PAUSING','PAUSED','STOPPING',
         'STOPPED','COMPLETED','INTERRUPTED','FAILED')),
    profile_key TEXT,
    profile_version TEXT,
    qc_profile_snapshot_json TEXT,
    ai_mode TEXT NOT NULL DEFAULT 'OFF' CHECK (ai_mode IN ('OFF','LOCAL')),
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    discovery_completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    error_code TEXT,
    error_message TEXT
);
CREATE INDEX idx_batches_project ON batches(project_id, created_at, id);

CREATE TABLE batch_items (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES batches(id),
    original_item_id TEXT REFERENCES batch_items(id),
    absolute_path TEXT NOT NULL,
    normalized_path_key TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    queue_position INTEGER,
    status TEXT NOT NULL CHECK (status IN
        ('PENDING','INSPECTING','RUNNING','COMPLETED','ERROR','CANCELLED','EXCLUDED')),
    import_size_bytes INTEGER,
    import_modified_at TEXT,
    media_asset_id TEXT REFERENCES media_assets(id),
    analysis_run_id TEXT UNIQUE REFERENCES analysis_runs(id),
    exclusion_reason TEXT,
    duplicate_count INTEGER NOT NULL DEFAULT 0 CHECK (duplicate_count >= 0),
    error_code TEXT,
    error_message TEXT,
    log_reference TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    UNIQUE(batch_id, normalized_path_key),
    UNIQUE(batch_id, queue_position),
    CHECK (queue_position IS NULL OR queue_position >= 1),
    CHECK (status != 'EXCLUDED' OR queue_position IS NULL)
);
CREATE INDEX idx_batch_items_state ON batch_items(batch_id, status, queue_position);

CREATE TABLE batch_reports (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES batches(id),
    report_type TEXT NOT NULL CHECK (report_type IN ('HTML','PDF')),
    relative_path TEXT NOT NULL UNIQUE,
    generated_at TEXT NOT NULL,
    generator_version TEXT NOT NULL,
    batch_revision INTEGER NOT NULL
);
CREATE INDEX idx_batch_reports_batch ON batch_reports(batch_id, generated_at, id);
