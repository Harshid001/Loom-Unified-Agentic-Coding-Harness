export interface ResolutionSummary {
  root_cause?: string;
  surgical_change?: string;
  verification_proof?: string;
}

export interface RunRecord {
  id: string;
  issue: string;
  status: string;
  cost: number;
  created_at: number;
  checkpoint: {
    run_id: string;
    issue_description: string;
    verification_passed: boolean;
    duration_seconds: number;
    created_at: string;
    patch_diff: string;
    reproduction_test: string;
    snapshot_id: string;
    resolution_summary?: ResolutionSummary;
    shared_data: {
      total_duration_ms: number;
      model: string;
      cost_report: {
        total_cost_usd: number;
      };
      ablations?: Array<{
        name: string;
        memory: boolean;
        context: boolean;
        multiAgent: boolean;
        passRate: string;
        cost: string;
      }>;
    };
  };
  trace_events: Array<{
    node_name: string;
    event_type: string;
    status: string;
    duration: number;
    cost: number;
  }>;
}

export const globalRunsStore: Map<string, RunRecord> = new Map();

/**
 * Creates an honest blocked run record when the Loom backend is unreachable.
 * Standalone mode CANNOT produce a VERIFIED SUCCESS state or fabricate synthetic diffs/hashes.
 */
export function createBlockedRunRecord(id: string, issue: string, model: string, backendUrl: string): RunRecord {
  const cleanIssue = issue.trim() || 'Target coding task';
  return {
    id,
    issue: cleanIssue,
    status: 'BLOCKED (Backend Offline)',
    cost: 0,
    created_at: Math.floor(Date.now() / 1000),
    checkpoint: {
      run_id: id,
      issue_description: cleanIssue,
      verification_passed: false,
      duration_seconds: 0,
      created_at: new Date().toISOString(),
      patch_diff: '',
      reproduction_test: '',
      snapshot_id: '',
      resolution_summary: {
        root_cause: `Loom harness backend is unreachable at ${backendUrl}. Execution cannot proceed without a live backend orchestrator.`,
        surgical_change: 'No code changes applied.',
        verification_proof: 'Sandbox verification not executed. Standalone mode does not fabricate mock verification results.',
      },
      shared_data: {
        total_duration_ms: 0,
        model,
        cost_report: {
          total_cost_usd: 0,
        },
      },
    },
    trace_events: [
      {
        node_name: 'system',
        event_type: `Backend Connection (${backendUrl})`,
        status: 'failed',
        duration: 0,
        cost: 0,
      },
    ],
  };
}
