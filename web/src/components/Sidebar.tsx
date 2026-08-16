import React, { useState, useMemo } from 'react';
import { Activity, GitBranch, FileCode, Layers, Clock, Play, CheckCircle2, XCircle, Loader2, Search, ChevronLeft, ChevronRight } from 'lucide-react';
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
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'pass' | 'fail' | 'exec'>('all');
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 5;

  const tabs = [
    { id: 'overview' as const, icon: Activity, label: 'Overview & Traces' },
    { id: 'dag' as const, icon: GitBranch, label: 'DAG Task Graph' },
    { id: 'diff' as const, icon: FileCode, label: 'Verified Patch' },
    { id: 'ablations' as const, icon: Layers, label: 'Ablation Studies' },
  ];

  const passedCount = runHistory.filter(r => r.status === 'VERIFIED SUCCESS').length;

  const filteredRuns = useMemo(() => {
    return runHistory.filter(r => {
      const matchesSearch = !searchQuery.trim() || 
        r.id.toLowerCase().includes(searchQuery.toLowerCase()) || 
        r.issue.toLowerCase().includes(searchQuery.toLowerCase());
      
      const isPass = r.status === 'VERIFIED SUCCESS';
      const isFail = r.status === 'FAILED';
      const isExec = !isPass && !isFail;

      if (!matchesSearch) return false;
      if (statusFilter === 'pass') return isPass;
      if (statusFilter === 'fail') return isFail;
      if (statusFilter === 'exec') return isExec;
      return true;
    });
  }, [runHistory, searchQuery, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredRuns.length / pageSize));
  const paginatedRuns = filteredRuns.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  return (
    <div className="w-64 flex flex-col gap-3 shrink-0" role="complementary" aria-label="Dashboard Sidebar">
      <div className="bg-[#111827] border border-gray-800 rounded-xl p-3">
        <h2 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Harness Views</h2>
        <nav className="space-y-0.5" role="tablist" aria-label="Harness Navigation Tabs">
          {tabs.map(tab => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              aria-controls={`tabpanel-${tab.id}`}
              id={`tab-${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              className={`w-full flex items-center gap-2 px-3 py-2 text-xs rounded-lg font-medium transition ${
                activeTab === tab.id
                  ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/30'
                  : 'text-gray-400 hover:bg-gray-800/50 hover:text-white border border-transparent'
              }`}
            >
              <tab.icon className="h-3.5 w-3.5" aria-hidden="true" /> {tab.label}
            </button>
          ))}
        </nav>
      </div>

      <div className="bg-[#111827] border border-gray-800 rounded-xl p-3 flex-1 flex flex-col min-h-0">
        <div className="flex items-center justify-between mb-2 px-1">
          <div className="flex items-center gap-1.5">
            <h2 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">Execution Runs</h2>
            <span className="text-[10px] font-mono text-gray-600 bg-gray-900 px-1.5 py-0.5 rounded">{runHistory.length}</span>
          </div>
        </div>

        {passedCount > 0 && (
          <div className="flex items-center gap-2 px-3 py-2 mb-2 bg-emerald-500/5 rounded-lg border border-emerald-500/10">
            <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
              <div className="h-full bg-emerald-500 rounded-full transition-all" style={{ width: `${(passedCount / runHistory.length) * 100}%` }} />
            </div>
            <span className="text-[10px] text-emerald-400 font-mono">{passedCount}/{runHistory.length} passed</span>
          </div>
        )}

        <div className="space-y-2 mb-2">
          <div className="relative">
            <Search className="h-3.5 w-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => { setSearchQuery(e.target.value); setCurrentPage(1); }}
              placeholder="Search runs..."
              className="w-full bg-gray-900/80 border border-gray-800 rounded-lg pl-8 pr-2.5 py-1.5 text-[11px] text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <div className="flex items-center gap-1">
            {(['all', 'pass', 'fail', 'exec'] as const).map(filter => (
              <button
                key={filter}
                onClick={() => { setStatusFilter(filter); setCurrentPage(1); }}
                className={`flex-1 py-1 text-[10px] uppercase font-semibold rounded transition ${
                  statusFilter === filter
                    ? 'bg-indigo-600/30 text-indigo-300 border border-indigo-500/40'
                    : 'bg-gray-900 text-gray-400 hover:text-gray-200 border border-gray-800/60'
                }`}
              >
                {filter}
              </button>
            ))}
          </div>
        </div>

        {isLoadingRuns ? (
          <div className="flex-1 flex items-center justify-center" aria-live="polite">
            <Loader2 className="h-5 w-5 text-gray-500 animate-spin" />
          </div>
        ) : filteredRuns.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-4 gap-2">
            <Play className="h-6 w-6 text-gray-700" />
            <p className="text-xs text-gray-600">No matching runs</p>
            <p className="text-[10px] text-gray-700">Adjust filters or create a run</p>
          </div>
        ) : (
          <div className="flex-1 flex flex-col min-h-0">
            <div className="space-y-1.5 overflow-y-auto flex-1 pr-1" role="listbox" aria-label="Recorded execution runs">
              {paginatedRuns.map((run) => {
                const isPassed = run.status === 'VERIFIED SUCCESS';
                return (
                  <button
                    key={run.id}
                    role="option"
                    aria-selected={selectedRun === run.id}
                    onClick={() => setSelectedRun(run.id)}
                    className={`w-full text-left p-2.5 rounded-lg border transition ${
                      selectedRun === run.id
                        ? 'bg-indigo-950/40 border-indigo-500/40 text-white'
                        : 'bg-gray-900/40 border-gray-800/60 text-gray-400 hover:bg-gray-800/50 hover:text-gray-200'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono text-[11px] text-indigo-400">{run.id}</span>
                      <span className={`text-[9px] px-1.5 py-0.5 rounded font-semibold uppercase tracking-wide ${
                        isPassed
                          ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
                          : run.status === 'FAILED'
                            ? 'bg-red-500/15 text-red-400 border border-red-500/20'
                            : 'bg-blue-500/15 text-blue-400 border border-blue-500/20'
                      }`}>
                        {isPassed ? <CheckCircle2 className="h-3 w-3 inline mr-0.5" /> : run.status === 'FAILED' ? <XCircle className="h-3 w-3 inline mr-0.5" /> : null}
                        {isPassed ? 'PASS' : run.status === 'FAILED' ? 'FAIL' : 'EXEC'}
                      </span>
                    </div>
                    <p className="text-[11px] line-clamp-2 text-gray-300 leading-relaxed">{run.issue}</p>
                    {run.cost !== undefined && (
                      <p className="text-[9px] text-gray-600 font-mono mt-1">${run.cost.toFixed(4)}</p>
                    )}
                  </button>
                );
              })}
            </div>
            {totalPages > 1 && (
              <div className="flex items-center justify-between pt-2 border-t border-gray-800/80 text-[10px] text-gray-400">
                <span>Page {currentPage} of {totalPages}</span>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className="p-1 rounded bg-gray-900 hover:bg-gray-800 disabled:opacity-30 border border-gray-800"
                    aria-label="Previous Page"
                  >
                    <ChevronLeft className="h-3 w-3" />
                  </button>
                  <button
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    className="p-1 rounded bg-gray-900 hover:bg-gray-800 disabled:opacity-30 border border-gray-800"
                    aria-label="Next Page"
                  >
                    <ChevronRight className="h-3 w-3" />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};