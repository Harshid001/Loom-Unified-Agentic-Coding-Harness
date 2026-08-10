import React from 'react';
import { ArrowRight, CheckCircle2 } from 'lucide-react';

interface DagTabProps {
  displayData: any;
}

export const DagTab: React.FC<DagTabProps> = ({ displayData }) => {
  if (!displayData) {
    return (
      <div className="flex-1 bg-[#111827] border border-gray-800 rounded-xl p-8 flex items-center justify-center text-gray-500 text-sm">
        Select a run to view its DAG Task Graph.
      </div>
    );
  }

  const nodes = [
    { id: 'onboarding', label: '1. Repo Mapper', detail: 'AST & Git History Index' },
    { id: 'reproduction', label: '2. Reproduction Agent', detail: 'Generate Test Script' },
    { id: 'patcher', label: '3. Patcher Agent', detail: 'LLM Code Patch Proposal' },
    { id: 'verifier', label: '4. Verification Runner', detail: 'Pytest Harness Execution' },
    { id: 'reviewer', label: '5. Evidence Reviewer', detail: 'Final Approval Gate' }
  ];

  return (
    <div className="flex-1 bg-[#111827] border border-gray-800 rounded-xl p-6 flex flex-col gap-6" id="tabpanel-dag" role="tabpanel" aria-labelledby="tab-dag">
      <div>
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">DAG Task Graph Topology</h3>
        <p className="text-xs text-gray-400">Sequential multi-agent execution pipeline with feedback loops</p>
      </div>

      <div className="flex-1 flex flex-col justify-center items-center gap-6 p-8 bg-gray-950/40 rounded-xl border border-gray-800/80">
        <div className="flex flex-wrap items-center justify-center gap-4 max-w-4xl">
          {nodes.map((node, i) => (
            <React.Fragment key={node.id}>
              <div className="flex flex-col items-center bg-gray-900 border border-indigo-500/30 px-4 py-3 rounded-xl shadow-lg shadow-indigo-950/20 text-center w-48">
                <CheckCircle2 className="h-5 w-5 text-emerald-400 mb-2" aria-hidden="true" />
                <span className="text-xs font-bold text-white mb-1">{node.label}</span>
                <span className="text-[11px] text-gray-400">{node.detail}</span>
              </div>
              {i < nodes.length - 1 && (
                <ArrowRight className="h-5 w-5 text-indigo-400/60 hidden md:block" aria-hidden="true" />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
};
