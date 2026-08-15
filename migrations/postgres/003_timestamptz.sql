-- Migration 003: TIMESTAMPTZ conversion and timestamp indexes for runs, steps, patches, and verification results
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'runs' AND column_name = 'started_at_tz'
    ) THEN
        ALTER TABLE runs ADD COLUMN started_at_tz TIMESTAMPTZ;
        ALTER TABLE runs ADD COLUMN completed_at_tz TIMESTAMPTZ;
        
        UPDATE runs SET started_at_tz = to_timestamp(started_at) WHERE started_at IS NOT NULL;
        UPDATE runs SET completed_at_tz = to_timestamp(completed_at) WHERE completed_at IS NOT NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'agent_steps' AND column_name = 'recorded_at_tz'
    ) THEN
        ALTER TABLE agent_steps ADD COLUMN recorded_at_tz TIMESTAMPTZ;
        UPDATE agent_steps SET recorded_at_tz = to_timestamp(recorded_at) WHERE recorded_at IS NOT NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'patches' AND column_name = 'recorded_at_tz'
    ) THEN
        ALTER TABLE patches ADD COLUMN recorded_at_tz TIMESTAMPTZ;
        UPDATE patches SET recorded_at_tz = to_timestamp(recorded_at) WHERE recorded_at IS NOT NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'verification_results' AND column_name = 'recorded_at_tz'
    ) THEN
        ALTER TABLE verification_results ADD COLUMN recorded_at_tz TIMESTAMPTZ;
        UPDATE verification_results SET recorded_at_tz = to_timestamp(recorded_at) WHERE recorded_at IS NOT NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_runs_started_at_tz ON runs(started_at_tz);
CREATE INDEX IF NOT EXISTS idx_agent_steps_recorded_at_tz ON agent_steps(recorded_at_tz);
CREATE INDEX IF NOT EXISTS idx_patches_recorded_at_tz ON patches(recorded_at_tz);
CREATE INDEX IF NOT EXISTS idx_verification_recorded_at_tz ON verification_results(recorded_at_tz);
