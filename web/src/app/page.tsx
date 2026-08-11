"use client";

import React, { useState, useCallback } from 'react';
import { useRuns } from '../hooks/useRuns';
import { Header } from '../components/Header';
import { Sidebar } from '../components/Sidebar';
import { OverviewTab } from '../components/OverviewTab';
import { DagTab } from '../components/DagTab';
import { DiffTab } from '../components/DiffTab';
import { AblationsTab } from '../components/AblationsTab';
import { LiveBox } from '../components/LiveBox';

const AVAILABLE_MODELS = [
  'claude-3-5-sonnet-20241022',
  'gpt-4o',
  'gpt-4o-mini',
  'gemini-1.5-pro',
  'deepseek-v3',
  'claude-3-opus-20240229',
];

export default function LoomDashboard() {
  const [activeTab, setActiveTab] = useState<'overview' | 'dag' | 'diff' | 'ablations'>('overview');
  const [isLiveBoxOpen, setIsLiveBoxOpen] = useState(false);
  const [selectedModel, setSelectedModel] = useState(AVAILABLE_MODELS[0]);
  const [newIssue, setNewIssue] = useState('');
  const [repoPath, setRepoPath] = useState('.');
  const [mockMode, setMockMode] = useState(true);
  const [notification, setNotification] = useState<string | null>(null);

  const {
    selectedRun,
    setSelectedRun,
    runHistory,
    selectedRunDetails,
    isLoadingRuns,
    isLoadingDetails,
    errorBanner,
    setErrorBanner,
    fetchRuns
  } = useRuns();

  const showNotification = useCallback((msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 5000);
  }, []);

  const handleOpenLiveBox = useCallback(() => {
    if (!newIssue.trim()) {
      setNewIssue('Fix calculation edge case in token cost tracker');
    }
    setIsLiveBoxOpen(true);
  }, [newIssue]);

  const handleRunComplete = useCallback((runId: string, success: boolean) => {
    if (success) {
      showNotification(`Run ${runId} completed successfully`);
    }
    fetchRuns();
  }, [fetchRuns, showNotification]);

  const handleRollback = useCallback(async () => {
    if (!selectedRun) return;
    try {
      const res = await fetch(`/api/rollback/${selectedRun}`, { method: 'POST' });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: 'Rollback failed' }));
        throw new Error(errData.detail || 'Rollback execution failed');
      }
      showNotification(`Rollback successful for run ${selectedRun}`);
    } catch (err: any) {
      setErrorBanner(`Rollback failed: ${err.message}`);
    }
  }, [selectedRun, showNotification, setErrorBanner]);

  const checkpoint = selectedRunDetails?.checkpoint;
  const traceEvents = selectedRunDetails?.trace_events || [];

  const displayData = checkpoint ? {
    id: checkpoint.run_id,
    issue: checkpoint.issue_description || 'No issue description available',
    status: checkpoint.verification_passed ? 'VERIFIED SUCCESS' : 'EXECUTED',
    duration: checkpoint.shared_data?.total_duration_ms
      ? `${(checkpoint.shared_data.total_duration_ms / 1000).toFixed(1)}s`
      : checkpoint.duration_seconds ? `${checkpoint.duration_seconds.toFixed(1)}s` : '--',
    cost: checkpoint.shared_data?.cost_report?.total_cost_usd
      ? `$${checkpoint.shared_data.cost_report.total_cost_usd.toFixed(4)}`
      : '--',
    model: checkpoint.shared_data?.model || selectedModel,
    nodes: traceEvents.length > 0 ? traceEvents.map((t: any) => ({
      name: t.node_name || 'step',
      label: t.event_type || 'Agent Execution',
      status: t.status || 'completed',
      duration: t.duration ? `${t.duration}s` : '--',
      cost: t.cost ? `$${t.cost.toFixed(4)}` : '--'
    })) : [
      { name: 'onboarding', label: 'Repo Mapper', status: 'pending', duration: '--', cost: '--' },
      { name: 'reproduction', label: 'Reproduction Agent', status: 'pending', duration: '--', cost: '--' },
      { name: 'patcher', label: 'Patcher Agent', status: 'pending', duration: '--', cost: '--' },
      { name: 'verifier', label: 'Verification Runner', status: 'pending', duration: '--', cost: '--' },
      { name: 'reviewer', label: 'Evidence Bundle Reviewer', status: 'pending', duration: '--', cost: '--' },
    ],
    patchDiff: checkpoint.patch_diff || 'No patch diff recorded for this run.',
    reproductionTest: checkpoint.reproduction_test,
    snapshotId: checkpoint.snapshot_id,
    createdAt: checkpoint.created_at,
  } : null;

  return (
    <div className="min-h-screen bg-[#0B0F19] text-gray-100 flex flex-col font-sans">
      <Header
        modelName={selectedModel}
        availableModels={AVAILABLE_MODELS}
        onModelChange={setSelectedModel}
        onOpenLiveBox={() => setIsLiveBoxOpen(true)}
        runCount={runHistory.length}
      />

      {notification && (
        <div className="bg-emerald-500/10 border-b border-emerald-500/30 px-6 py-2.5 text-xs text-emerald-400 font-medium flex items-center justify-between animate-in slide-in-from-top-2" role="status">
          <span>{notification}</span>
          <button onClick={() => setNotification(null)} className="text-emerald-500 hover:text-emerald-300 text-sm">✕</button>
        </div>
      )}

      {errorBanner && (
        <div className="bg-amber-500/10 border-b border-amber-500/30 px-6 py-2.5 text-xs text-amber-400 font-mono flex items-center justify-between" role="alert">
          <span>{errorBanner}</span>
          <button onClick={() => setErrorBanner(null)} className="text-amber-500 hover:text-amber-300" aria-label="Dismiss error notification">✕</button>
        </div>
      )}

      {!displayData && !isLoadingRuns && runHistory.length === 0 && (
        <div className="bg-[#0d1321] border-b border-gray-800 px-6 py-3 flex items-center gap-4 flex-wrap">
          <div className="flex-1 min-w-[300px]">
            <input
              type="text"
              value={newIssue}
              onChange={e => setNewIssue(e.target.value)}
              placeholder="Enter issue description (e.g. Fix memory leak in telemetry tracer)..."
              className="w-full bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-xs text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
              onKeyDown={e => { if (e.key === 'Enter' && newIssue.trim()) handleOpenLiveBox(); }}
            />
          </div>
          <select
            value={selectedModel}
            onChange={e => setSelectedModel(e.target.value)}
            className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {AVAILABLE_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <label className="flex items-center gap-2 text-xs text-gray-400">
            <input type="checkbox" checked={mockMode} onChange={e => setMockMode(e.target.checked)} className="rounded bg-gray-800 border-gray-700" />
            Mock mode
          </label>
          <button
            onClick={handleOpenLiveBox}
            disabled={!newIssue.trim()}
            className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white rounded-lg text-xs font-medium transition shadow-lg shadow-indigo-600/20"
          >
            Execute Pipeline
          </button>
        </div>
      )}

      <main className="flex-1 flex max-w-7xl w-full mx-auto p-6 gap-6">
        <Sidebar
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          runHistory={runHistory}
          selectedRun={selectedRun}
          setSelectedRun={setSelectedRun}
          isLoadingRuns={isLoadingRuns}
        />

        <section className="flex-1 flex flex-col min-w-0">
          {activeTab === 'overview' && (
            <OverviewTab
              displayData={displayData}
              selectedRun={selectedRun}
              onRollback={handleRollback}
              isLoadingDetails={isLoadingDetails}
            />
          )}
          {activeTab === 'dag' && <DagTab displayData={displayData} />}
          {activeTab === 'diff' && <DiffTab displayData={displayData} />}
          {activeTab === 'ablations' && <AblationsTab displayData={displayData} />}
        </section>
      </main>

      <LiveBox
        isOpen={isLiveBoxOpen}
        onClose={() => setIsLiveBoxOpen(false)}
        issue={newIssue}
        model={selectedModel}
        repoPath={repoPath}
        mockMode={mockMode}
        onRunComplete={handleRunComplete}
      />
    </div>
  );
}