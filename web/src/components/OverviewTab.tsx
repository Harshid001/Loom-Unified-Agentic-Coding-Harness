import React, { useState } from 'react';
import { Terminal, ShieldCheck, Clock, DollarSign, RotateCcw, CheckCircle2, XCircle, Loader2, AlertTriangle, Copy, ExternalLink, ChevronRight } from 'lucide-react';

interface OverviewTabProps {
  displayData: any;
  selectedRun: string | null;
  onRollback: () => void;
  isLoadingDetails: boolean;
}

export const OverviewTab: React.FC<OverviewTabProps> = ({ displayData, selectedRun, onRollback, isLoadingDetails }) => {
  const [expandedLog, setExpandedLog] = useState<string | null>(null);

  if (isLoadingDetails) {
    return (
      <div className="flex-1 bg-[#111827] border border-gray-800 rounded-xl p-8 flex items-center justify-center gap-3 text-gray-400">
        <Loader2 className="h-5 w-5 animate-spin text-indigo-400" />
        <span className="text-sm">Loading run details...</span>
      </div>
    );
  }

  if (!displayData) {
    return (
      <div className="flex-1 bg-[#111827] border border-gray-800 rounded-xl p-8 flex flex-col items-center justify-center text-gray-500 gap-3">
        <div className="h-16 w-16 rounded-2xl bg-gray-800/50 flex items-center justify-center">
          <Terminal className="h-7 w-7 text-gray-600" />
        </div>
        <p className="text-sm font-medium">No execution run selected</p>
        <p className="text-xs text-gray-600">Select an execution run from the sidebar to inspect traces, or click + New Run to start one.</p>
      </div>
    );
  }

  const isSuccess = displayData.status === 'VERIFIED SUCCESS';
  const costValue = displayData.cost !== '--' ? parseFloat(displayData.cost.replace('$', '')) : 0;

  return (
    <div className="flex-1 flex flex-col gap-5" id="tabpanel-overview" role="tabpanel" aria-labelledby="tab-overview">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-4 flex items-center gap-3 hover:border-gray-700 transition">
          <div className="p-2.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Terminal className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">Run ID</p>
            <p className="text-sm font-mono font-semibold text-white truncate">{displayData.id}</p>
          </div>
        </div>

        <div className="bg-[#111827] border border-gray-800 rounded-xl p-4 flex items-center gap-3 hover:border-gray-700 transition">
          <div className={`p-2.5 rounded-lg border ${isSuccess ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'}`}>
            {isSuccess ? <ShieldCheck className="h-5 w-5" aria-hidden="true" /> : <AlertTriangle className="h-5 w-5" aria-hidden="true" />}
          </div>
          <div>
            <p className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">Verification</p>
            <p className={`text-xs font-bold uppercase tracking-wide ${isSuccess ? 'text-emerald-400' : 'text-red-400'}`}>{displayData.status}</p>
          </div>
        </div>

        <div className="bg-[#111827] border border-gray-800 rounded-xl p-4 flex items-center gap-3 hover:border-gray-700 transition">
          <div className="p-2.5 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <Clock className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <p className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">Duration</p>
            <p className="text-sm font-mono font-semibold text-white">{displayData.duration}</p>
          </div>
        </div>

        <div className="bg-[#111827] border border-gray-800 rounded-xl p-4 flex items-center gap-3 hover:border-gray-700 transition">
          <div className="p-2.5 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <DollarSign className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <p className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">Total Cost</p>
            <p className="text-sm font-mono font-semibold text-white">{displayData.cost}</p>
          </div>
        </div>
      </div>

      <div className="bg-[#111827] border border-gray-800 rounded-xl p-5 flex items-center justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h3 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Target Issue Description</h3>
          <p className="text-sm text-gray-200 leading-relaxed">{displayData.issue}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[10px] text-gray-500 font-mono bg-gray-900 px-2 py-1 rounded border border-gray-800">Model: {displayData.model}</span>
          {displayData.snapshotId && (
            <span className="text-[10px] text-gray-500 font-mono bg-gray-900 px-2 py-1 rounded border border-gray-800">Snapshot: {displayData.snapshotId}</span>
          )}
          <button
            onClick={onRollback}
            aria-label={`Rollback workspace for run ${selectedRun}`}
            className="flex items-center gap-1.5 text-xs bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 px-3 py-1.5 rounded-lg font-medium transition focus:ring-2 focus:ring-red-400 focus:outline-none"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" /> Rollback
          </button>
        </div>
      </div>

      <div className="bg-[#111827] border border-gray-800 rounded-xl p-5 flex-1 flex flex-col">
        <h3 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-4">Evidence Trace Pipeline Execution</h3>
        <div className="space-y-2 flex-1">
          {displayData.nodes.map((node: any, idx: number) => {
            const isRunning = node.status === 'running';
            const isDone = node.status === 'completed';
            const isFailed = node.status === 'failed';
            const isExpanded = expandedLog === node.name;

            return (
              <div key={idx}>
                <button
                  onClick={() => setExpandedLog(isExpanded ? null : node.name)}
                  className={`w-full flex items-center justify-between p-3 rounded-lg border transition ${
                    isRunning ? 'bg-amber-500/5 border-amber-500/20' :
                    isDone ? 'bg-gray-900/60 border-gray-800 hover:border-gray-700' :
                    isFailed ? 'bg-red-500/5 border-red-500/20' :
                    'bg-gray-900/60 border-gray-800/50'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    {isRunning ? (
                      <Loader2 className="h-4 w-4 text-amber-400 animate-spin" aria-hidden="true" />
                    ) : isDone ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-400" aria-hidden="true" />
                    ) : isFailed ? (
                      <XCircle className="h-4 w-4 text-red-400" aria-hidden="true" />
                    ) : (
                      <div className="h-4 w-4 rounded-full border-2 border-gray-600" />
                    )}
                    <div>
                      <p className="text-xs font-mono text-indigo-400">{node.name}</p>
                      <p className="text-xs text-gray-300 font-medium">{node.label}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 text-xs font-mono text-gray-400">
                    <span>{node.duration}</span>
                    <span>{node.cost}</span>
                    <ChevronRight className={`h-3.5 w-3.5 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                  </div>
                </button>
                {isExpanded && (
                  <div className="mx-4 mt-1 mb-2 p-3 bg-gray-950 rounded-lg border border-gray-800 text-xs font-mono text-gray-400 space-y-1">
                    <div className="flex items-center gap-2 text-gray-500">
                      <span>Status: <span className={isDone ? 'text-emerald-400' : isFailed ? 'text-red-400' : 'text-amber-400'}>{node.status}</span></span>
                    </div>
                    <p>{node.duration !== '--' ? `Completed in ${node.duration}` : 'Awaiting execution...'}</p>
                    <p>{node.cost !== '--' ? `Cost: ${node.cost}` : 'Cost: pending'}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};