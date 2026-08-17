"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { useRuns } from '../hooks/useRuns';
import { useGitHub } from '../hooks/useGitHub';
import { Header } from '../components/Header';
import { Sidebar, LifecycleTab } from '../components/Sidebar';
import { OverviewTab } from '../components/OverviewTab';
import { DagTab } from '../components/DagTab';
import { DiffTab } from '../components/DiffTab';
import { AblationsTab } from '../components/AblationsTab';
import { EvidenceView } from '../components/EvidenceView';
import { LiveBoxReal } from '../components/LiveBoxReal';
import { AuthGate } from '../components/AuthGate';
import { RepoConnectModal } from '../components/RepoConnectModal';
import { GitHubIssuesDrawer } from '../components/GitHubIssuesDrawer';
import { NewRunModal } from '../components/NewRunModal';
import {
  FolderGit2,
  GitBranch,
  ListTodo,
  Cpu,
  Box,
  TestTube2,
  ShieldCheck,
  Play,
  FileCode,
  CheckCircle2,
  XCircle,
  Clock,
  Terminal,
} from 'lucide-react';

const AVAILABLE_MODELS = [
  'claude-3-7-sonnet-20250219',
  'claude-3-5-sonnet-20241022',
  'gpt-4o',
  'gpt-4o-mini',
  'gemini-1.5-pro',
  'gemini-1.5-flash',
  'deepseek-v3',
  'claude-3-opus-20240229',
];

function LoomControlPlane() {
  const [activeTab, setActiveTab] = useState<LifecycleTab>('overview');
  const [isLiveBoxOpen, setIsLiveBoxOpen] = useState(false);
  const [isNewRunModalOpen, setIsNewRunModalOpen] = useState(false);
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

  const repoPath = connectedRepo?.fullName || '';

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

  // Synchronize model settings with backend
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
                { name: 'onboarding', label: 'Repo Mapper', status: checkpoint.verification_passed ? 'completed' : 'pending', duration: '--', cost: '--' },
                { name: 'reproduction', label: 'Reproduction Agent', status: checkpoint.verification_passed ? 'completed' : 'pending', duration: '--', cost: '--' },
                { name: 'patcher', label: 'Patcher Agent', status: checkpoint.verification_passed ? 'completed' : 'pending', duration: '--', cost: '--' },
                { name: 'verifier', label: 'Verification Runner', status: checkpoint.verification_passed ? 'completed' : 'pending', duration: '--', cost: '--' },
                { name: 'reviewer', label: 'Evidence Bundle Reviewer', status: checkpoint.verification_passed ? 'completed' : 'pending', duration: '--', cost: '--' },
              ],
        patchDiff: checkpoint.patch_diff || '',
        reproductionTest: checkpoint.reproduction_test,
        snapshotId: checkpoint.snapshot_id,
        createdAt: checkpoint.created_at,
        ablations: checkpoint.shared_data?.ablations,
      }
    : null;

  return (
    <div className="min-h-screen flex flex-col font-sans">
      {/* 1. Top Operational Bar */}
      <Header
        modelName={selectedModel}
        availableModels={availableModels}
        onModelChange={handleModelChange}
        onOpenLiveBox={() => setIsNewRunModalOpen(true)}
        onOpenRepoModal={() => setIsRepoModalOpen(true)}
        onOpenIssuesDrawer={() => setIsIssuesDrawerOpen(true)}
        connectedRepo={connectedRepo}
        githubUser={githubUser}
        runCount={runHistory.length}
      />

      {notification && (
        <div className="bg-[var(--success)]/10 border-b border-[var(--success)]/30 px-6 py-2 text-xs text-[var(--success)] font-medium font-mono" role="status">
          ✓ {notification}
        </div>
      )}
      {errorBanner && (
        <div className="bg-[var(--danger)]/10 border-b border-[var(--danger)]/30 px-6 py-2 text-xs text-[var(--danger)] font-mono" role="alert">
          ⚠ {errorBanner}
        </div>
      )}

      {/* 2. Main Control Plane Layout (Sidebar + Center Content) */}
      <div className="flex-1 flex max-w-[1400px] w-full mx-auto p-8 gap-8">
        <Sidebar
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          runHistory={runHistory}
          selectedRun={selectedRun}
          setSelectedRun={setSelectedRun}
          isLoadingRuns={isLoadingRuns}
          onOpenRepoModal={() => setIsRepoModalOpen(true)}
          connectedRepoName={connectedRepo?.fullName || 'No Repository Connected'}
        />

        <main className="flex-1 flex flex-col min-w-0">
          {/* View: Overview & Live Active Run */}
          {activeTab === 'overview' && (
            <OverviewTab
              displayData={displayData}
              selectedRun={selectedRun}
              onRollback={handleRollback}
              isLoadingDetails={isLoadingDetails}
              onOpenLiveBox={() => setIsNewRunModalOpen(true)}
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

          {/* View: Runs Feed */}
          {activeTab === 'runs' && (
            <div className="loom-card flex flex-col gap-4">
              <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-3">
                <div>
                  <h2 className="text-base font-bold text-[var(--text-primary)] font-mono uppercase">
                    Execution Runs History
                  </h2>
                  <p className="text-xs text-[var(--text-muted)] mt-0.5">
                    Chronological ledger of multi-agent DAG runs for {connectedRepo?.fullName || 'this workspace'}
                  </p>
                </div>
                <button
                  onClick={() => setIsNewRunModalOpen(true)}
                  className="btn-primary h-8 px-3.5 text-xs gap-1.5"
                >
                  <Play className="h-3 w-3 fill-current" />
                  <span>Launch Run</span>
                </button>
              </div>

              {runHistory.length > 0 ? (
                <div className="space-y-2">
                  {runHistory.map(r => (
                    <div
                      key={r.id}
                      onClick={() => {
                        setSelectedRun(r.id);
                        setActiveTab('overview');
                      }}
                      className="p-4 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-subtle)] hover:border-[var(--border-default)] hover:bg-[var(--bg-hover)] transition cursor-pointer flex items-center justify-between gap-4"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-mono text-xs font-bold text-[var(--brand-hover)]">{r.id}</span>
                          <span className={`status-pill ${r.status === 'VERIFIED SUCCESS' ? 'status-pill-verified' : r.status === 'FAILED' ? 'status-pill-failed' : 'status-pill-running'} text-[10px]`}>
                            {r.status}
                          </span>
                        </div>
                        <p className="text-xs text-[var(--text-primary)] font-sans">{r.issue}</p>
                      </div>
                      <div className="text-right font-mono text-xs text-[var(--text-muted)] shrink-0">
                        <span>{r.cost ? `$${r.cost.toFixed(4)}` : '--'}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="py-12 text-center text-xs text-[var(--text-muted)] flex flex-col items-center gap-3">
                  <p>No execution runs recorded yet for {connectedRepo?.fullName || 'this repository'}.</p>
                  <button
                    onClick={() => setIsNewRunModalOpen(true)}
                    className="btn-primary h-8 px-3 text-xs gap-1.5"
                  >
                    <Play className="h-3 w-3 fill-current" />
                    <span>Launch First Run</span>
                  </button>
                </div>
              )}
            </div>
          )}

          {/* View: DAG Execution */}
          {activeTab === 'dag' && (
            <DagTab displayData={displayData} onOpenLiveBox={() => setIsNewRunModalOpen(true)} />
          )}

          {/* View: Agents Architecture */}
          {activeTab === 'agents' && (
            <div className="loom-card flex flex-col gap-6">
              <div className="border-b border-[var(--border-subtle)] pb-3">
                <h2 className="text-base font-bold text-[var(--text-primary)] font-mono uppercase">
                  Multi-Agent Architecture
                </h2>
                <p className="text-xs text-[var(--text-muted)] mt-0.5">
                  Specialized agent roles coordinated under the DAG harness for {connectedRepo?.fullName || 'current workspace'}
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {[
                  { name: 'Repo Mapper Agent', role: 'Tree-Sitter AST & Call Graph Proximity', model: 'Tree-Sitter AST', budget: 'Symbol Indexer' },
                  { name: 'Reproduction Agent', role: 'Failing Test Synthesis (Red Phase)', model: selectedModel, budget: '16,000 tokens' },
                  { name: 'Patcher Agent', role: 'Surgical Unified Code Modification', model: selectedModel, budget: '32,000 tokens' },
                  { name: 'Verifier Agent', role: 'Isolated Container Pytest Execution', model: 'Sandbox Tier B', budget: 'Strict Isolation' },
                  { name: 'Reviewer Agent', role: 'SHA-256 Hash Chain Proof Construction', model: 'Cryptographic Proof Engine', budget: '5 artifacts' },
                ].map((agent, i) => (
                  <div key={i} className="p-4 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-subtle)] space-y-2">
                    <div className="flex items-center gap-2 text-[var(--brand)]">
                      <Cpu className="h-4 w-4" />
                      <h3 className="text-xs font-bold font-mono text-[var(--text-primary)]">{agent.name}</h3>
                    </div>
                    <p className="text-xs text-[var(--text-secondary)]">{agent.role}</p>
                    <div className="pt-2 border-t border-[var(--border-subtle)] flex items-center justify-between text-[10px] font-mono text-[var(--text-muted)]">
                      <span>Model: {agent.model}</span>
                      <span>Config: {agent.budget}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* View: Sandbox Isolation */}
          {activeTab === 'sandbox' && (
            <div className="loom-card flex flex-col gap-6">
              <div className="border-b border-[var(--border-subtle)] pb-3">
                <h2 className="text-base font-bold text-[var(--text-primary)] font-mono uppercase">
                  Sandbox Tier Isolation
                </h2>
                <p className="text-xs text-[var(--text-muted)] mt-0.5">
                  Execution isolation configured for {connectedRepo?.fullName || 'current workspace'}
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="p-4 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-subtle)] space-y-2">
                  <span className="text-[10px] font-mono font-bold text-[var(--brand)]">TIER A</span>
                  <h3 className="text-sm font-bold text-[var(--text-primary)] font-mono">Git Worktree</h3>
                  <p className="text-xs text-[var(--text-muted)]">Fastest checkout for read-only AST indexing and static lint analysis.</p>
                </div>

                <div className="p-4 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-default)] ring-1 ring-[var(--brand)]/30 space-y-2">
                  <span className="text-[10px] font-mono font-bold text-[var(--cyan)]">TIER B (ACTIVE)</span>
                  <h3 className="text-sm font-bold text-[var(--text-primary)] font-mono">Container (gVisor)</h3>
                  <p className="text-xs text-[var(--text-muted)]">Isolated container with strict DENY_ALL egress and syscall filtering.</p>
                </div>

                <div className="p-4 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-subtle)] space-y-2">
                  <span className="text-[10px] font-mono font-bold text-[var(--warning)]">TIER C</span>
                  <h3 className="text-sm font-bold text-[var(--text-primary)] font-mono">Firecracker MicroVM</h3>
                  <p className="text-xs text-[var(--text-muted)]">Hardware-level virtualization for adversarial patch executions.</p>
                </div>
              </div>
            </div>
          )}

          {/* View: Patches / Diff */}
          {activeTab === 'diff' && (
            <DiffTab displayData={displayData} onOpenLiveBox={() => setIsNewRunModalOpen(true)} />
          )}

          {/* View: Tests */}
          {activeTab === 'tests' && (
            <div className="loom-card flex flex-col gap-4">
              <div className="border-b border-[var(--border-subtle)] pb-3 flex items-center justify-between">
                <div>
                  <h2 className="text-base font-bold text-[var(--text-primary)] font-mono uppercase">
                    Reproduction & Sandbox Test Suites
                  </h2>
                  <p className="text-xs text-[var(--text-muted)] mt-0.5">
                    Red-phase synthesis and green-phase verification test traces
                  </p>
                </div>
                {displayData && (
                  <span className={`status-pill ${displayData.status === 'VERIFIED SUCCESS' ? 'status-pill-verified' : 'status-pill-running'} text-[10px]`}>
                    {displayData.status === 'VERIFIED SUCCESS' ? 'VERIFIED PASSED' : 'EXECUTING'}
                  </span>
                )}
              </div>

              {displayData?.reproductionTest ? (
                <div className="bg-[var(--bg-root)] border border-[var(--border-subtle)] rounded-xl p-4 font-mono text-xs text-[var(--text-secondary)] overflow-x-auto space-y-2">
                  <p className="text-[var(--brand)] font-bold">{'// Synthesized Reproduction Test for Run '}{displayData.id}:</p>
                  <pre className="whitespace-pre-wrap text-[var(--text-primary)]">{displayData.reproductionTest}</pre>
                </div>
              ) : (
                <div className="py-12 text-center text-xs text-[var(--text-muted)] flex flex-col items-center gap-3">
                  <p>No test suite execution recorded yet for {connectedRepo?.fullName || 'this repository'}.</p>
                  <button
                    onClick={() => setIsNewRunModalOpen(true)}
                    className="btn-primary h-8 px-3 text-xs gap-1.5"
                  >
                    <Play className="h-3 w-3 fill-current" />
                    <span>Launch Run to Synthesize Tests</span>
                  </button>
                </div>
              )}
            </div>
          )}

          {/* View: Evidence Proof Layer */}
          {activeTab === 'evidence' && (
            <EvidenceView
              displayData={displayData}
              runId={displayData?.id || selectedRun || undefined}
              connectedRepoName={connectedRepo?.fullName}
              onOpenLiveBox={() => setIsNewRunModalOpen(true)}
            />
          )}

          {/* View: Ablations */}
          {activeTab === 'ablations' && (
            <AblationsTab displayData={displayData} />
          )}
        </main>
      </div>

      {/* New Run Modal */}
      <NewRunModal
        isOpen={isNewRunModalOpen}
        onClose={() => setIsNewRunModalOpen(false)}
        newIssue={newIssue}
        setNewIssue={setNewIssue}
        isExecuting={false}
        onSubmit={() => {
          setIsNewRunModalOpen(false);
          setIsLiveBoxOpen(true);
        }}
        repoName={connectedRepo?.fullName || 'No Repository Connected'}
        branchName={connectedRepo?.selectedBranch || 'main'}
        onOpenIssuesDrawer={() => setIsIssuesDrawerOpen(true)}
      />

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
      <LoomControlPlane />
    </AuthGate>
  );
}
