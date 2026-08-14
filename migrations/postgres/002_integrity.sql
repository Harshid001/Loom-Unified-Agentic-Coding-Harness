DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'agent_steps' AND constraint_name = 'fk_agent_steps_run'
    ) THEN
        ALTER TABLE agent_steps
        ADD CONSTRAINT fk_agent_steps_run FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'patches' AND constraint_name = 'fk_patches_run'
    ) THEN
        ALTER TABLE patches
        ADD CONSTRAINT fk_patches_run FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'verification_results' AND constraint_name = 'fk_verification_results_run'
    ) THEN
        ALTER TABLE verification_results
        ADD CONSTRAINT fk_verification_results_run FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_agent_steps_run_recorded ON agent_steps(run_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_patches_run_recorded ON patches(run_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_verification_run_recorded ON verification_results(run_id, recorded_at);
