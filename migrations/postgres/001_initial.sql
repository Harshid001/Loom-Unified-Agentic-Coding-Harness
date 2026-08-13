CREATE TABLE IF NOT EXISTS runs (
    run_id VARCHAR PRIMARY KEY,
    org_id VARCHAR NOT NULL DEFAULT 'default',
    repo_id VARCHAR,
    issue_text TEXT,
    status VARCHAR,
    sandbox_tier VARCHAR,
    model_sequence TEXT,
    verification_passed BOOLEAN,
    confidence_score DOUBLE PRECISION,
    merge_decision TEXT,
    cost_usd DOUBLE PRECISION,
    started_at DOUBLE PRECISION,
    completed_at DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS agent_steps (
    id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL,
    agent_name VARCHAR,
    input_context_ref VARCHAR,
    output_ref TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    model_id VARCHAR,
    duration_ms INTEGER,
    retry_count INTEGER,
    context_truncated BOOLEAN,
    status VARCHAR,
    recorded_at DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_steps_run ON agent_steps(run_id);

CREATE TABLE IF NOT EXISTS patches (
    id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL,
    diff_hash VARCHAR,
    diff_ref TEXT,
    files_touched INTEGER,
    risk_flags TEXT,
    apply_status VARCHAR,
    recorded_at DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_patches_run ON patches(run_id);

CREATE TABLE IF NOT EXISTS verification_results (
    id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL,
    stage VARCHAR,
    status VARCHAR,
    evidence_ref TEXT,
    details TEXT,
    recorded_at DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_verify_run ON verification_results(run_id);
