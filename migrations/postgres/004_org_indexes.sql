-- Migration 004: Org and timestamp composite indexes for runs and steps (PRD-020)
CREATE INDEX IF NOT EXISTS idx_runs_org_started ON runs(org_id, started_at);
CREATE INDEX IF NOT EXISTS idx_runs_org_started_tz ON runs(org_id, started_at_tz);
CREATE INDEX IF NOT EXISTS idx_agent_steps_run_recorded ON agent_steps(run_id, recorded_at);
