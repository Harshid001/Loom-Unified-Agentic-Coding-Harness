import React from 'react';
import { Activity, GitBranch, FileCode, Layers, Clock } from 'lucide-react';
import { RunItem } from '../hooks/useRuns';

interface SidebarProps {
  activeTab: 'overview' | 'dag' | 'diff' | 'ablations';
  setActiveTab: (tab: 'overview' | 'dag' | 'diff' | 'ablations') => void;
  runHistory: RunItem[];
  selectedRun: string | null;
  setSelectedRun: (id: string) => void;
  isLoadingRuns: boolean;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  runHistory,
  selectedRun,
  setSelectedRun,
  isLoadingRuns
}) => {
  return (
    <div className="w-64 flex flex-col gap-4" role="complementary" aria-label="Dashboard Sidebar">
      <div className="bg-[#111827] border border-gray-800 rounded-xl p-4">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Harness Views</h2>
        <nav className="space-y-1" role="tablist" aria-label="Harness Navigation Tabs">
          <button
            role="tab"
            aria-selected={activeTab === 'overview'}
            aria-controls="tabpanel-overview"
            id="tab-overview"
            onClick={() => setActiveTab('overview')}
            className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm rounded-lg font-medium transition focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
              activeTab === 'overview' ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/30' : 'text-gray-400 hover:bg-gray-800/50 hover:text-white'
            }`}
          >
            <Activity className="h-4 w-4" aria-hidden="true" /> Overview & Traces
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'dag'}
            aria-controls="tabpanel-dag"
            id="tab-dag"
            onClick={() => setActiveTab('dag')}
            className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm rounded-lg font-medium transition focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
              activeTab === 'dag' ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/30' : 'text-gray-400 hover:bg-gray-800/50 hover:text-white'
            }`}
          >
            <GitBranch className="h-4 w-4" aria-hidden="true" /> DAG Task Graph
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'diff'}
            aria-controls="tabpanel-diff"
            id="tab-diff"
            onClick={() => setActiveTab('diff')}
            className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm rounded-lg font-medium transition focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
              activeTab === 'diff' ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/30' : 'text-gray-400 hover:bg-gray-800/50 hover:text-white'
            }`}
          >
            <FileCode className="h-4 w-4" aria-hidden="true" /> Verified Patch
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'ablations'}
            aria-controls="tabpanel-ablations"
            id="tab-ablations"
            onClick={() => setActiveTab('ablations')}
            className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm rounded-lg font-medium transition focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
              activeTab === 'ablations' ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/30' : 'text-gray-400 hover:bg-gray-800/50 hover:text-white'
            }`}
          >
            <Layers className="h-4 w-4" aria-hidden="true" /> Ablation Studies
          </button>
        </nav>
      </div>

      <div className="bg-[#111827] border border-gray-800 rounded-xl p-4 flex-1 flex flex-col">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center justify-between">
          <span>Execution Runs</span>
          <Clock className="h-3.5 w-3.5 text-gray-500" aria-hidden="true" />
        </h2>
        
        {isLoadingRuns ? (
          <div className="flex-1 flex items-center justify-center text-xs text-gray-500" aria-live="polite">
            Loading run history...
          </div>
        ) : runHistory.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-xs text-gray-500 text-center p-4">
            No runs recorded yet. Start a new run above.
          </div>
        ) : (
          <div className="space-y-2 overflow-y-auto flex-1 pr-1" role="listbox" aria-label="Recorded execution runs">
            {runHistory.map((run) => (
              <button
                key={run.id}
                role="option"
                aria-selected={selectedRun === run.id}
                onClick={() => setSelectedRun(run.id)}
                className={`w-full text-left p-3 rounded-lg border transition focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
                  selectedRun === run.id
                    ? 'bg-indigo-950/40 border-indigo-500/40 text-white'
                    : 'bg-gray-900/50 border-gray-800/80 text-gray-400 hover:bg-gray-800/50 hover:text-gray-200'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-xs text-indigo-400">{run.id}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                    run.status === 'VERIFIED SUCCESS'
                      ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                      : 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                  }`}>
                    {run.status === 'VERIFIED SUCCESS' ? 'PASSED' : 'EXECUTED'}
                  </span>
                </div>
                <p className="text-xs line-clamp-2 text-gray-300 font-normal">{run.issue}</p>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
