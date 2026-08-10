import React from 'react';
import { Terminal, ShieldCheck, Clock, DollarSign, RotateCcw, CheckCircle2, XCircle } from 'lucide-react';

interface OverviewTabProps {
  displayData: any;
  selectedRun: string | null;
  onRollback: () => void;
}

export const OverviewTab: React.FC<OverviewTabProps> = ({ displayData, selectedRun, onRollback }) => {
  if (!displayData) {
    return (
      <div className="flex-1 bg-[#111827] border border-gray-800 rounded-xl p-8 flex items-center justify-center text-gray-500 text-sm">
        Select an execution run from the sidebar to inspect traces.
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col gap-6" id="tabpanel-overview" role="tabpanel" aria-labelledby="tab-overview">
      {/* Metrics Banner */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-4 flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Terminal className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <p className="text-xs text-gray-400 font-medium">Run ID</p>
            <p className="text-sm font-mono font-semibold text-white">{displayData.id}</p>
          </div>
        </div>

        <div className="bg-[#111827] border border-gray-800 rounded-xl p-4 flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <ShieldCheck className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <p className="text-xs text-gray-400 font-medium">Verification Status</p>
            <p className="text-xs font-semibold text-emerald-400 uppercase tracking-wide">{displayData.status}</p>
          </div>
        </div>

        <div className="bg-[#111827] border border-gray-800 rounded-xl p-4 flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <Clock className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <p className="text-xs text-gray-400 font-medium">Execution Duration</p>
            <p className="text-sm font-mono font-semibold text-white">{displayData.duration}</p>
          </div>
        </div>

        <div className="bg-[#111827] border border-gray-800 rounded-xl p-4 flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <DollarSign className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <p className="text-xs text-gray-400 font-medium">Total Cost</p>
            <p className="text-sm font-mono font-semibold text-white">{displayData.cost}</p>
          </div>
        </div>
      </div>

      {/* Target Issue & Actions */}
      <div className="bg-[#111827] border border-gray-800 rounded-xl p-5 flex items-center justify-between">
        <div>
          <h3 className="text-xs font-semibold text-indigo-400 uppercase tracking-wider mb-1">Target Issue Description</h3>
          <p className="text-sm text-gray-200">{displayData.issue}</p>
        </div>
        <button
          onClick={onRollback}
          aria-label={`Rollback workspace for run ${selectedRun}`}
          className="flex items-center gap-2 text-xs bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 px-3.5 py-2 rounded-lg font-medium transition focus:ring-2 focus:ring-red-400 focus:outline-none"
        >
          <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" /> Rollback Workspace
        </button>
      </div>

      {/* Trace Pipeline Table */}
      <div className="bg-[#111827] border border-gray-800 rounded-xl p-5 flex-1">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-4">Evidence Trace Pipeline Execution</h3>
        <div className="space-y-3">
          {displayData.nodes.map((node: any, idx: number) => (
            <div key={idx} className="flex items-center justify-between p-3 rounded-lg bg-gray-900/60 border border-gray-800">
              <div className="flex items-center gap-3">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" aria-hidden="true" />
                <div>
                  <p className="text-xs font-mono text-indigo-400">{node.name}</p>
                  <p className="text-xs text-gray-300 font-medium">{node.label}</p>
                </div>
              </div>
              <div className="flex items-center gap-4 text-xs font-mono text-gray-400">
                <span>{node.duration}</span>
                <span>{node.cost}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
