CREATE TABLE ai_reviews (
    id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    model_id TEXT,
    model_version TEXT,
    prompt_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('COMPLETED', 'UNAVAILABLE')),
    error_code TEXT,
    output_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(finding_id)
);

CREATE INDEX idx_ai_reviews_finding ON ai_reviews(finding_id);
