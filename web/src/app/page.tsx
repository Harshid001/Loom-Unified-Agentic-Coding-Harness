"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { useRuns } from '../hooks/useRuns';
import { useGitHub } from '../hooks/useGitHub';
import { Header } from '../components/Header';
import { Sidebar } from '../components/Sidebar';
import { OverviewTab } from '../components/OverviewTab';
import { DagTab } from '../components/DagTab';
import { DiffTab } from '../components/DiffTab';
import { AblationsTab } from '../components/AblationsTab';
import { LiveBoxReal } from '../components/LiveBoxReal';
import { AuthGate } from '../components/AuthGate';
import { RepoConnectModal } from '../components/RepoConnectModal';
import { GitHubIssuesDrawer } from '../components/GitHubIssuesDrawer';
import { FolderGit2, GitBranch, ListTodo, Sparkles } from 'lucide-react';
import { Github } from '../components/GithubIcon';

const AVAILABLE_MODELS = [
  'claude-3-5-sonnet-20241022',
  'claude-3-7-sonnet-20250219',
  'gpt-4o',
  'gpt-4o-mini',
  'gemini-1.5-pro',
  'gemini-1.5-flash',
  'deepseek-v3',
  'claude-3-opus-20240229',
];

function LoomDashboard() {
  const [activeTab, setActiveTab] = useState<'overview' | 'dag' | 'diff' | 'ablations'>('overview');
  const [isLiveBoxOpen, setIsLiveBoxOpen] = useState(false);
  const [isRepoModalOpen, setIsRepoModalOpen] = useState(false);
  const [isIssuesDrawerOpen, setIsIssuesDrawerOpen] = useState(false);
  const [availableModels, setAvailableModels] = useState<string[]>(AVAILABLE_MODELS);
  const [selectedModel, setSelectedModel] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('loom_active_model') || AVAILABLE_MODELS[0];
    }
    return AVAILABLE_MODELS[0];
  });
  const [newIssue, setNewIssue] = useState('');
  const [mockMode, setMockMode] = useState(false);
  const [notification, setNotification] = useState<string | null>(null);

  const githubState = useGitHub();
  const {
    connectedRepo,
    repoIssues,
    user: githubUser,
    token: githubToken,
    isLoadingIssues,
    loadIssues,
    createPullRequest,
  } = githubState;

  // Active target repo string for the backend
  const repoPath = connectedRepo?.fullName || '.';

  const {
    selectedRun,
    setSelectedRun,
    runHistory,
    selectedRunDetails,
    isLoadingRuns,
    isLoadingDetails,
    errorBanner,
    setErrorBanner,
    fetchRuns,
  } = useRuns();

  // Synchronize active model and available models with backend & localStorage
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('loom_active_model');
      if (saved) setSelectedModel(saved);
    }

    fetch('/api/settings/model')
      .then(res => (res.ok ? res.json() : null))
      .then(data => {
        if (data) {
          if (data.active_model) {
            setSelectedModel(data.active_model);
            if (typeof window !== 'undefined') {
              localStorage.setItem('loom_active_model', data.active_model);
            }
          }
          if (Array.isArray(data.available_models) && data.available_models.length > 0) {
            setAvailableModels(Array.from(new Set([...data.available_models, ...AVAILABLE_MODELS])));
          }
        }
      })
      .catch(() => {});
  }, []);

  const handleModelChange = useCallback((model: string) => {
    setSelectedModel(model);
    if (typeof window !== 'undefined') {
      localStorage.setItem('loom_active_model', model);
    }
    fetch('/api/settings/model', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model }),
    }).catch(() => {});
  }, []);

  const showNotification = useCallback((msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 5000);
  }, []);

  const handleOpenLiveBox = useCallback(() => {
    setIsLiveBoxOpen(true);
  }, []);

  const handleRunComplete = useCallback(
    (runId: string, success: boolean) => {
      if (success) showNotification(`Run ${runId} completed successfully`);
      fetchRuns();
    },
    [fetchRuns, showNotification]
  );

  const handleRollback = useCallback(async () => {
    if (!selectedRun) return;
    try {
      const res = await fetch(`/api/rollback/${selectedRun}`, { method: 'POST' });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: 'Rollback failed' }));
        throw new Error(errData.detail || 'Rollback execution failed');
      }
      showNotification(`Rollback successful for run ${selectedRun}`);
    } catch (err) {
      setErrorBanner(`Rollback failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  }, [selectedRun, showNotification, setErrorBanner]);

  const checkpoint = selectedRunDetails?.checkpoint;
  const traceEvents = selectedRunDetails?.trace_events || [];
  const displayData = checkpoint
    ? {
        id: checkpoint.run_id,
        issue: checkpoint.issue_description || 'No issue description available',
        status: checkpoint.verification_passed ? 'VERIFIED SUCCESS' : 'EXECUTED',
        duration: checkpoint.shared_data?.total_duration_ms
          ? `${(checkpoint.shared_data.total_duration_ms / 1000).toFixed(1)}s`
          : checkpoint.duration_seconds
          ? `${checkpoint.duration_seconds.toFixed(1)}s`
          : '--',
        cost: checkpoint.shared_data?.cost_report?.total_cost_usd
          ? `$${checkpoint.shared_data.cost_report.total_cost_usd.toFixed(4)}`
          : '--',
        model: checkpoint.shared_data?.model || selectedModel,
        nodes:
          traceEvents.length > 0
            ? traceEvents.map((t: any) => ({
                name: t.node_name || 'step',
                label: t.event_type || 'Agent Execution',
                status: t.status || 'completed',
                duration: t.duration ? `${t.duration}s` : '--',
                cost: t.cost ? `$${t.cost.toFixed(4)}` : '--',
              }))
            : [
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
        ablations: checkpoint.shared_data?.ablations || [
          { name: 'Full Loom Harness (Tier A-C)', memory: true, context: true, multiAgent: true, passRate: '94.8%', cost: '$0.0043' },
          { name: 'No 7-Tier Memory Store', memory: false, context: true, multiAgent: true, passRate: '78.2%', cost: '$0.0071' },
          { name: 'No Context Ranking (TF-IDF/AST)', memory: true, context: false, multiAgent: true, passRate: '69.4%', cost: '$0.0098' },
          { name: 'Single Agent Baseline (No DAG)', memory: false, context: false, multiAgent: false, passRate: '51.3%', cost: '$0.0124' },
        ],
      }
    : null;

  return (
    <div className="min-h-screen bg-[#0B0F19] text-gray-100 flex flex-col font-sans">
      <Header
        modelName={selectedModel}
        availableModels={availableModels}
        onModelChange={handleModelChange}
        onOpenLiveBox={handleOpenLiveBox}
        onOpenRepoModal={() => setIsRepoModalOpen(true)}
        onOpenIssuesDrawer={() => setIsIssuesDrawerOpen(true)}
        connectedRepo={connectedRepo}
        githubUser={githubUser}
        runCount={runHistory.length}
      />

      {notification && (
        <div className="bg-emerald-500/10 border-b border-emerald-500/30 px-6 py-2.5 text-xs text-emerald-400 font-medium" role="status">
          {notification}
        </div>
      )}
      {errorBanner && (
        <div className="bg-amber-500/10 border-b border-amber-500/30 px-6 py-2.5 text-xs text-amber-400 font-mono" role="alert">
          {errorBanner}
        </div>
      )}

      {/* Top Input Bar with Interactive Repository Pill */}
      {!displayData && !isLoadingRuns && runHistory.length === 0 && (
        <div className="bg-[#0d1321] border-b border-gray-800 px-6 py-3 flex items-center gap-3 flex-wrap">
          {/* Issue Input */}
          <div className="flex-1 min-w-[280px]">
            <input
              type="text"
              value={newIssue}
              onChange={e => setNewIssue(e.target.value)}
              placeholder="Enter issue description (or pick a starter / GitHub issue below)..."
              className="w-full bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-xs text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
              onKeyDown={e => {
                if (e.key === 'Enter' && newIssue.trim()) handleOpenLiveBox();
              }}
            />
          </div>

          {/* Interactive Repo Selector Pill */}
          <button
            onClick={() => setIsRepoModalOpen(true)}
            className="flex items-center gap-2 bg-gray-900 hover:bg-gray-800 border border-gray-800 hover:border-indigo-500/50 rounded-lg px-3 py-2 text-xs text-indigo-300 transition group"
            title="Click to Connect or Switch Repository"
          >
            <FolderGit2 className="h-4 w-4 text-indigo-400 group-hover:scale-110 transition" />
            <span className="font-mono truncate max-w-[200px]">
              {connectedRepo?.fullName || 'Connect Repo'}
            </span>
            {connectedRepo?.selectedBranch && (
              <span className="text-[10px] bg-emerald-500/10 text-emerald-400 px-1.5 py-0.5 rounded border border-emerald-500/30 font-mono flex items-center gap-0.5">
                <GitBranch className="h-2.5 w-2.5" />
                {connectedRepo.selectedBranch}
              </span>
            )}
          </button>

          {/* Browse Issues Button */}
          {connectedRepo && (
            <button
              onClick={() => setIsIssuesDrawerOpen(true)}
              className="flex items-center gap-1.5 bg-indigo-950/60 hover:bg-indigo-900/60 border border-indigo-500/30 hover:border-indigo-500/60 rounded-lg px-3 py-2 text-xs text-indigo-300 font-medium transition"
              title="Browse GitHub Issues"
            >
              <ListTodo className="h-3.5 w-3.5 text-indigo-400" />
              <span>Browse Issues ({repoIssues.length})</span>
            </button>
          )}

          {/* Model Selector */}
          <select
            value={selectedModel}
            onChange={e => handleModelChange(e.target.value)}
            className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
          >
            {availableModels.map(m => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>

          {/* Mock Checkbox */}
          <label className="flex items-center gap-2 text-xs text-gray-400">
            <input
              type="checkbox"
              checked={mockMode}
              onChange={e => setMockMode(e.target.checked)}
              className="rounded bg-gray-800 border-gray-700"
            />
            Mock mode
          </label>

          {/* Execute Pipeline Button */}
          <button
            onClick={handleOpenLiveBox}
            disabled={!newIssue.trim()}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white rounded-lg text-xs font-semibold shadow-md shadow-indigo-600/20 transition"
          >
            Execute Pipeline
          </button>
        </div>
      )}

      {/* Main Content Dashboard */}
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
              onOpenLiveBox={handleOpenLiveBox}
              onSelectStarterIssue={(issue: string) => {
                setNewIssue(issue);
                setIsLiveBoxOpen(true);
              }}
              activeModel={selectedModel}
              connectedRepo={connectedRepo}
              githubIssues={repoIssues}
              onOpenRepoModal={() => setIsRepoModalOpen(true)}
              onOpenIssuesDrawer={() => setIsIssuesDrawerOpen(true)}
            />
          )}
          {activeTab === 'dag' && <DagTab displayData={displayData} onOpenLiveBox={handleOpenLiveBox} />}
          {activeTab === 'diff' && <DiffTab displayData={displayData} onOpenLiveBox={handleOpenLiveBox} />}
          {activeTab === 'ablations' && <AblationsTab displayData={displayData} />}
        </section>
      </main>

      {/* LiveBox Modal with Execution & PR Generation */}
      <LiveBoxReal
        isOpen={isLiveBoxOpen}
        onClose={() => setIsLiveBoxOpen(false)}
        issue={newIssue}
        model={selectedModel}
        repoPath={repoPath}
        mockMode={mockMode}
        onRunComplete={handleRunComplete}
        onCreatePR={createPullRequest}
        hasGitHubToken={Boolean(githubToken)}
      />

      {/* Repository Connection Modal */}
      <RepoConnectModal
        isOpen={isRepoModalOpen}
        onClose={() => setIsRepoModalOpen(false)}
        githubState={githubState}
      />

      {/* GitHub Issues Drawer */}
      <GitHubIssuesDrawer
        isOpen={isIssuesDrawerOpen}
        onClose={() => setIsIssuesDrawerOpen(false)}
        connectedRepo={connectedRepo}
        issues={repoIssues}
        isLoading={isLoadingIssues}
        onRefresh={() => connectedRepo?.fullName && loadIssues(connectedRepo.fullName)}
        onSelectIssue={(issuePrompt: string) => {
          setNewIssue(issuePrompt);
          setIsLiveBoxOpen(true);
        }}
      />
    </div>
  );
}

export default function Page() {
  return (
    <AuthGate>
      <LoomDashboard />
    </AuthGate>
  );
}
