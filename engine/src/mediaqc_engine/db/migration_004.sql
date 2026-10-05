CREATE TABLE audio_assignments (
    analysis_run_id TEXT PRIMARY KEY REFERENCES analysis_runs(id) ON DELETE CASCADE,
    identity TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    provenance TEXT NOT NULL,
    policy_version TEXT NOT NULL CHECK(policy_version='explicit_audio_v1'),
    document_json TEXT NOT NULL
);
CREATE TABLE audio_assignment_channels (
    analysis_run_id TEXT NOT NULL REFERENCES audio_assignments(analysis_run_id) ON DELETE CASCADE,
    stream_index INTEGER NOT NULL,
    channel_index INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('mix','iso','other','unknown')),
    expectation TEXT NOT NULL CHECK(expectation IN ('expected','unused','unknown')),
    PRIMARY KEY(analysis_run_id,stream_index,channel_index)
);
CREATE TABLE audio_assignment_programs (
    analysis_run_id TEXT NOT NULL REFERENCES audio_assignments(analysis_run_id) ON DELETE CASCADE,
    program_id TEXT NOT NULL,
    layout TEXT NOT NULL CHECK(layout IN ('mono','stereo')),
    PRIMARY KEY(analysis_run_id,program_id)
);
CREATE TABLE audio_assignment_members (
    analysis_run_id TEXT NOT NULL,
    program_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    stream_index INTEGER NOT NULL,
    channel_index INTEGER NOT NULL,
    PRIMARY KEY(analysis_run_id,program_id,ordinal),
    UNIQUE(analysis_run_id,program_id,stream_index,channel_index),
    FOREIGN KEY(analysis_run_id,program_id) REFERENCES audio_assignment_programs(analysis_run_id,program_id) ON DELETE CASCADE,
    FOREIGN KEY(analysis_run_id,stream_index,channel_index) REFERENCES audio_assignment_channels(analysis_run_id,stream_index,channel_index)
);
CREATE TRIGGER audio_assignment_immutable BEFORE UPDATE ON audio_assignments BEGIN SELECT RAISE(ABORT,'Immutable assignment'); END;
CREATE TRIGGER audio_channels_immutable BEFORE UPDATE ON audio_assignment_channels BEGIN SELECT RAISE(ABORT,'Immutable assignment'); END;
CREATE TRIGGER audio_programs_immutable BEFORE UPDATE ON audio_assignment_programs BEGIN SELECT RAISE(ABORT,'Immutable assignment'); END;
CREATE TRIGGER audio_members_immutable BEFORE UPDATE ON audio_assignment_members BEGIN SELECT RAISE(ABORT,'Immutable assignment'); END;
