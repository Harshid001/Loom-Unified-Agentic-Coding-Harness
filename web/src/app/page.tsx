"use client";

import { useState, useEffect, useCallback, useRef } from 'react';
import { useRuns } from '../hooks/useRuns';
import { useActiveRun } from '../hooks/useActiveRun';
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
import { ApiKeyModal } from '../components/ApiKeyModal';
import { RepoConnectModal } from '../components/RepoConnectModal';
import { GitHubIssuesDrawer } from '../components/GitHubIssuesDrawer';
import { NewRunModal } from '../components/NewRunModal';
import { AnalyticsTab } from '../components/AnalyticsTab';
import { OnboardingTour } from '../components/OnboardingTour';
import { KeyboardShortcutsHelp } from '../components/KeyboardShortcutsHelp';
import { MobileBottomNav } from '../components/MobileBottomNav';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';
import {
  FolderGit2,
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
  ArrowRight,
  Zap,
  Lock,
} from 'lucide-react';

const AVAILABLE_MODELS = [
  'auto',
  'claude-3-7-sonnet-20250219',
  'gpt-4o',
  'gemini-3.1-pro-preview',
  'gemini-3.5-flash',
  'gemini-3.7-flash',
  'deepseek-v3',
  'deepseek-chat',
  'deepseek-reasoner',
  'claude-3-opus-20240229',
  'gpt-4o-mini',
];

type ToastVariant = 'success' | 'error';

interface ToastItem {
  id: number;
  message: string;
  variant: ToastVariant;
  exiting?: boolean;
}

function LoomControlPlane() {
  const [activeTab, setActiveTab] = useState<LifecycleTab>('overview');
  const [isLiveBoxOpen, setIsLiveBoxOpen] = useState(false);
  const [isNewRunModalOpen, setIsNewRunModalOpen] = useState(false);
  const [isRepoModalOpen, setIsRepoModalOpen] = useState(false);
  const [isApiKeyModalOpen, setIsApiKeyModalOpen] = useState(false);
  const [isIssuesDrawerOpen, setIsIssuesDrawerOpen] = useState(false);
  const [isKeyboardHelpOpen, setIsKeyboardHelpOpen] = useState(false);
  const [availableModels, setAvailableModels] = useState<string[]>(AVAILABLE_MODELS);
  const [selectedModel, setSelectedModel] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('loom_active_model') || AVAILABLE_MODELS[0];
    }
    return AVAILABLE_MODELS[0];
  });
  const [newIssue, setNewIssue] = useState('');
  const [mockMode, setMockMode] = useState(false);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const toastIdRef = useRef(0);

  const activeRun = useActiveRun();

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

  const repoPath = connectedRepo?.htmlUrl || connectedRepo?.fullName || '';

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

  useKeyboardShortcuts({
    onNewRun: () => setIsNewRunModalOpen(true),
    onEvidence: () => setActiveTab('evidence'),
    onAnalytics: () => setActiveTab('analytics'),
    onEscape: () => {
      setIsNewRunModalOpen(false);
      setIsLiveBoxOpen(false);
      setIsRepoModalOpen(false);
      setIsApiKeyModalOpen(false);
      setIsIssuesDrawerOpen(false);
      setIsKeyboardHelpOpen(false);
    },
    onSwitchTab: (idx) => {
      const tabs: LifecycleTab[] = ['overview', 'analytics', 'dag', 'agents', 'sandbox', 'diff', 'tests', 'evidence', 'ablations'];
      if (tabs[idx]) setActiveTab(tabs[idx]);
    },
    tabCount: 9,
  });

  // Handle Cmd+/ for keyboard shortcuts help
  useEffect(() => {
    const handleCmdSlash = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === '/') {
        e.preventDefault();
        setIsKeyboardHelpOpen(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleCmdSlash);
    return () => window.removeEventListener('keydown', handleCmdSlash);
  }, []);

  // Model sync
  useEffect(() => {
    const syncActiveModel = () => {
      if (typeof window !== 'undefined') {
        const saved = localStorage.getItem('loom_active_model');
        if (saved) setSelectedModel(saved);
      }
    };

    syncActiveModel();

    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'loom_active_model' && e.newValue) {
        setSelectedModel(e.newValue);
      }
    };

    const handleCustomModelChange = (e: Event) => {
      const customEvent = e as CustomEvent<string>;
      if (customEvent.detail) {
        setSelectedModel(customEvent.detail);
      }
    };

    window.addEventListener('storage', handleStorageChange);
    window.addEventListener('loom_active_model_changed', handleCustomModelChange);

    fetch('/api/settings/model')
      .then(res => (res.ok ? res.json() : null))
      .then(data => {
        if (data) {
          const localSaved = typeof window !== 'undefined' ? localStorage.getItem('loom_active_model') : null;
          if (data.active_model && !localSaved) {
            setSelectedModel(data.active_model);
            if (typeof window !== 'undefined') {
              localStorage.setItem('loom_active_model', data.active_model);
            }
          } else if (localSaved) {
            setSelectedModel(localSaved);
          }
          if (Array.isArray(data.available_models) && data.available_models.length > 0) {
            setAvailableModels(Array.from(new Set([...data.available_models, ...AVAILABLE_MODELS])));
          }
        }
      })
      .catch(() => {});

    return () => {
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('loom_active_model_changed', handleCustomModelChange);
    };
  }, []);

  const handleModelChange = useCallback((model: string) => {
    setSelectedModel(model);
    if (typeof window !== 'undefined') {
      localStorage.setItem('loom_active_model', model);
      window.dispatchEvent(new CustomEvent('loom_active_model_changed', { detail: model }));
    }
    fetch('/api/settings/model', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model }),
    }).catch(() => {});
  }, []);

  const showToast = useCallback((message: string, variant: ToastVariant = 'success') => {
    const id = ++toastIdRef.current;
    setToasts(prev => [...prev, { id, message, variant }]);
    setTimeout(() => {
      setToasts(prev => prev.map(t => t.id === id ? { ...t, exiting: true } : t));
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id));
      }, 250);
    }, 5000);
  }, []);

  const handleOpenLiveBox = useCallback(() => {
    setIsNewRunModalOpen(true);
  }, []);

  const handleRunComplete = useCallback(
    (runId: string, success: boolean) => {
      if (success) showToast(`Run ${runId} completed successfully`, 'success');
      else showToast(`Run ${runId} completed with issues`, 'error');
      fetchRuns();
    },
    [showToast, fetchRuns]
  );

  const handleRollback = useCallback(async () => {
    if (!selectedRun) return;
    try {
      const res = await fetch(`/api/rollback/${selectedRun}`, { method: 'POST' });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: 'Rollback failed' }));
        throw new Error(errData.detail || 'Rollback execution failed');
      }
      showToast(`Rollback successful for run ${selectedRun}`, 'success');
    } catch (err) {
      setErrorBanner(`Rollback failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
      showToast(`Rollback failed`, 'error');
    }
  }, [selectedRun, showToast, setErrorBanner]);

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
      <Header
        modelName={selectedModel}
        availableModels={availableModels}
        onModelChange={handleModelChange}
        onOpenLiveBox={handleOpenLiveBox}
        onOpenApiKeyModal={() => setIsApiKeyModalOpen(true)}
        onOpenRepoModal={() => setIsRepoModalOpen(true)}
        onOpenIssuesDrawer={() => setIsIssuesDrawerOpen(true)}
        connectedRepo={connectedRepo}
        githubUser={githubUser}
        runCount={runHistory.length}
        isExecuting={activeRun.isActive}
        activeRunStage={activeRun.currentStage}
        activeRunProgress={activeRun.currentStageIndex}
        activeRunTotal={activeRun.totalStages}
        activeRunElapsed={activeRun.elapsedFormatted}
        activeRunId={activeRun.activeRunId}
      />

      {/* Notification Banner (legacy top bar — kept as subtle strip) */}
      {errorBanner && (
        <div
          className="bg-[var(--danger)]/10 border-b border-[var(--danger)]/30 px-6 py-2 text-xs text-[var(--danger)] font-medium font-mono animate-slide-in-from-top"
          role="alert"
        >
          ⚠ {errorBanner}
          <button onClick={() => setErrorBanner(null)} className="ml-3 hover:underline">Dismiss</button>
        </div>
      )}

      {/* ── Main Control Plane Layout ── */}
      <div className="flex-1 flex max-w-[1440px] w-full mx-auto px-4 sm:px-6 lg:px-8 py-5 gap-5">
        <Sidebar
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          runHistory={runHistory}
          selectedRun={selectedRun}
          setSelectedRun={setSelectedRun}
          isLoadingRuns={isLoadingRuns}
          onOpenRepoModal={() => setIsRepoModalOpen(true)}
          onOpenApiKeyModal={() => setIsApiKeyModalOpen(true)}
          connectedRepoName={connectedRepo?.fullName || 'No Repository Connected'}
        />

        <main className="flex-1 flex flex-col min-w-0 gap-5 animate-fade-in">
          {/* View: Overview & Live Active Run */}
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

          {/* View: Analytics Dashboard */}
          {activeTab === 'analytics' && (
            <AnalyticsTab runHistory={runHistory} connectedRepoName={connectedRepo?.fullName || 'Workspace'} />
          )}

          {/* View: DAG Execution */}
          {activeTab === 'dag' && (
            <DagTab displayData={displayData} activeModel={selectedModel} onOpenLiveBox={() => setIsNewRunModalOpen(true)} />
          )}

          {/* View: Agents Architecture */}
          {activeTab === 'agents' && (
            <div className="loom-card-elevated flex flex-col gap-6 animate-fade-in">
              <div className="border-b border-[var(--border-subtle)] pb-3">
                <h2 className="text-base font-bold text-[var(--text-primary)] font-mono uppercase tracking-tight">
                  Multi-Agent Architecture
                </h2>
                <p className="text-xs text-[var(--text-muted)] mt-0.5">
                  Specialized agent roles coordinated under the DAG harness for {connectedRepo?.fullName || 'current workspace'}
                </p>
              </div>

              {/* DAG flow visualization */}
              <div className="grid grid-cols-1 gap-3">
                {[
                  { name: 'Repo Mapper Agent', role: 'Tree-Sitter AST & Call Graph Proximity', model: 'Tree-Sitter AST', budget: 'Symbol Indexer', accent: 'var(--brand)', icon: FileCode },
                  { name: 'Reproduction Agent', role: 'Failing Test Synthesis (Red Phase)', model: selectedModel, budget: '16,000 tokens', accent: 'var(--cyan)', icon: TestTube2 },
                  { name: 'Patcher Agent', role: 'Surgical Unified Code Modification', model: selectedModel, budget: '32,000 tokens', accent: 'var(--brand-hover)', icon: FileCode },
                  { name: 'Verifier Agent', role: 'Isolated Container Pytest Execution', model: 'Sandbox Tier B', budget: 'Strict Isolation', accent: 'var(--success)', icon: ShieldCheck },
                  { name: 'Reviewer Agent', role: 'SHA-256 Hash Chain Proof Construction', model: 'Cryptographic Proof Engine', budget: '5 artifacts', accent: 'var(--warning)', icon: CheckCircle2 },
                ].map((agent, i, arr) => {
                  const Icon = agent.icon;
                  const isActive = displayData && displayData.nodes?.[i]?.status === 'completed';
                  return (
                    <div key={i} style={{ animationDelay: `${i * 80}ms` }} className="animate-fade-in">
                      {/* Flow arrow between agents */}
                      {i < arr.length - 1 && (
                        <div className="absolute -bottom-3 left-1/2 -translate-x-1/2 z-10 hidden sm:flex items-center gap-1 text-[var(--text-muted)]">
                          <div className="h-4 w-px bg-[var(--border-default)]" />
                          <ArrowRight className="h-3 w-3" aria-hidden="true" />
                        </div>
                      )}
                      <div
                        className={`p-4 rounded-xl border-l-[3px] transition-all duration-200 hover:shadow-lg ${
                          isActive
                            ? 'bg-[var(--bg-elevated)] border-[var(--border-subtle)] shadow-[0_0_16px_rgba(124,92,255,0.08)]'
                            : 'bg-[var(--bg-elevated)] border border-[var(--border-subtle)] opacity-80'
                        }`}
                        style={{ borderLeftColor: agent.accent }}
                      >
                        <div className="flex items-center gap-2.5 mb-1.5">
                          <div
                            className="h-7 w-7 rounded-lg flex items-center justify-center shrink-0"
                            style={{ backgroundColor: `${agent.accent}20`, color: agent.accent }}
                          >
                            <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                          </div>
                          <h3 className="text-xs font-bold font-mono text-[var(--text-primary)]">{agent.name}</h3>
                          {isActive && (
                            <span className="status-pill status-pill-verified text-[8px] py-0 ml-auto">DONE</span>
                          )}
                        </div>
                        <p className="text-xs text-[var(--text-secondary)] mb-2.5 ml-[2.85rem]">{agent.role}</p>
                        <div className="flex items-center gap-3 text-[10px] font-mono text-[var(--text-muted)] ml-[2.85rem]">
                          <span className="flex items-center gap-1">
                            <Cpu className="h-3 w-3" aria-hidden="true" />
                            {agent.model}
                          </span>
                          <span className="text-[var(--border-default)]">|</span>
                          <span className="flex items-center gap-1">
                            <Terminal className="h-3 w-3" aria-hidden="true" />
                            {agent.budget}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* View: Sandbox Isolation */}
          {activeTab === 'sandbox' && (
            <div className="loom-card-elevated flex flex-col gap-6 animate-fade-in">
              <div className="border-b border-[var(--border-subtle)] pb-3">
                <h2 className="text-base font-bold text-[var(--text-primary)] font-mono uppercase tracking-tight">
                  Sandbox Tier Isolation
                </h2>
                <p className="text-xs text-[var(--text-muted)] mt-0.5">
                  Execution isolation configured for {connectedRepo?.fullName || 'current workspace'}
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {[
                  { tier: 'TIER A', name: 'Git Worktree', icon: Zap, color: 'var(--text-muted)', accent: 'var(--text-muted)', desc: 'Fastest checkout for read-only AST indexing and static lint analysis.', features: ['Zero isolation overhead', 'Local filesystem access', 'Tree-sitter AST parsing'], active: false },
                  { tier: 'TIER B', name: 'Container (gVisor)', icon: Box, color: 'var(--cyan)', accent: 'var(--cyan)', desc: 'Isolated container with strict DENY_ALL egress and syscall filtering.', features: ['gVisor kernel interception', 'DENY_ALL network egress', 'Pytest sandbox execution'], active: true },
                  { tier: 'TIER C', name: 'Firecracker MicroVM', icon: Lock, color: 'var(--warning)', accent: 'var(--warning)', desc: 'Hardware-level virtualization for adversarial patch executions.', features: ['KVM hardware isolation', 'MSHV hypervisor (Windows)', 'Full memory snapshot'], active: false },
                ].map(tier => {
                  const Icon = tier.icon;
                  return (
                    <div
                      key={tier.tier}
                      className={`loom-card p-4 rounded-xl border space-y-3 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg ${
                        tier.active
                          ? 'loom-card-active'
                          : 'border-[var(--border-subtle)] hover:border-[var(--border-default)]'
                      }`}
                      style={tier.active ? { borderColor: 'rgba(0,212,255,0.4)' } : undefined}
                    >
                      <div className="flex items-center gap-2">
                        <div
                          className="h-7 w-7 rounded-lg flex items-center justify-center"
                          style={{ backgroundColor: `${tier.accent}15`, color: tier.accent }}
                        >
                          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                        </div>
                        <div>
                          <span className="text-[9px] font-mono font-bold uppercase tracking-wider" style={{ color: tier.accent }}>
                            {tier.tier} {tier.active && '(ACTIVE)'}
                          </span>
                          <h3 className="text-sm font-bold text-[var(--text-primary)] font-mono leading-tight">{tier.name}</h3>
                        </div>
                      </div>
                      <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">{tier.desc}</p>
                      <ul className="space-y-1.5">
                        {tier.features.map(f => (
                          <li key={f} className="flex items-center gap-1.5 text-[10px] font-mono text-[var(--text-muted)]">
                            <CheckCircle2 className="h-3 w-3 shrink-0" style={{ color: tier.accent }} aria-hidden="true" />
                            {f}
                          </li>
                        ))}
                      </ul>
                      {tier.active && (
                        <div className="flex items-center gap-1.5 pt-2 border-t border-[var(--cyan)]/20">
                          <Lock className="h-3 w-3 text-[var(--cyan)]" aria-hidden="true" />
                          <span className="text-[10px] font-mono text-[var(--cyan)] font-bold">DENY_ALL EGRESS</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* View: Patches / Diff */}
          {activeTab === 'diff' && (
            <DiffTab displayData={displayData} onOpenLiveBox={() => setIsNewRunModalOpen(true)} />
          )}

          {/* View: Tests */}
          {activeTab === 'tests' && (
            <div className="loom-card-elevated flex flex-col gap-4 animate-fade-in">
              <div className="border-b border-[var(--border-subtle)] pb-3 flex items-center justify-between">
                <div>
                  <h2 className="text-base font-bold text-[var(--text-primary)] font-mono uppercase tracking-tight">
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
                  <p className="text-[var(--brand)] font-bold">{`// Synthesized Reproduction Test for Run `}{displayData.id}:</p>
                  <pre className="whitespace-pre-wrap text-[var(--text-primary)]">{displayData.reproductionTest}</pre>
                </div>
              ) : (
                <div className="py-14 text-center text-xs text-[var(--text-muted)] flex flex-col items-center gap-3">
                  <div className="h-10 w-10 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-subtle)] flex items-center justify-center text-[var(--text-muted)]">
                    <TestTube2 className="h-5 w-5" aria-hidden="true" />
                  </div>
                  <p>No test suite execution recorded yet for {connectedRepo?.fullName || 'this repository'}.</p>
                  <button
                    onClick={() => setIsNewRunModalOpen(true)}
                    className="btn-primary h-8 px-3 text-xs gap-1.5 shadow-lg shadow-[var(--brand)]/20"
                  >
                    <Play className="h-3 w-3 fill-current relative z-10" />
                    <span className="relative z-10">Launch Run to Synthesize Tests</span>
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

      {/* ── Modals / Drawers ── */}
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
        activeModel={selectedModel}
        availableModels={availableModels}
        onModelChange={handleModelChange}
        onOpenIssuesDrawer={() => setIsIssuesDrawerOpen(true)}
      />

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
        availableModels={availableModels}
        onModelChange={handleModelChange}
        onOpenApiKeyModal={() => setIsApiKeyModalOpen(true)}
      />

      <ApiKeyModal
        isOpen={isApiKeyModalOpen}
        onClose={() => setIsApiKeyModalOpen(false)}
      />

      <RepoConnectModal
        isOpen={isRepoModalOpen}
        onClose={() => setIsRepoModalOpen(false)}
        githubState={githubState}
      />

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

      <KeyboardShortcutsHelp
        isOpen={isKeyboardHelpOpen}
        onClose={() => setIsKeyboardHelpOpen(false)}
      />

      <OnboardingTour />

      <MobileBottomNav
        activeTab={activeTab}
        onSelectTab={(t) => setActiveTab(t as LifecycleTab)}
        onOpenSettings={() => setIsRepoModalOpen(true)}
      />

      {/* ── Toast Notifications ── */}
      <div className="fixed bottom-5 right-5 z-[100] flex flex-col gap-2 pointer-events-none" aria-live="polite">
        {toasts.map(toast => (
          <div
            key={toast.id}
            role="status"
            className={`notification-toast ${toast.variant === 'success' ? 'toast-success' : 'toast-error'} ${toast.exiting ? 'toast-exit' : ''}`}
          >
            <div className="flex items-start gap-2 flex-1">
              {toast.variant === 'success'
                ? <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
                : <XCircle className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
              }
              <span className="text-[11px] font-mono leading-snug">{toast.message}</span>
            </div>
            <div className="toast-progress" />
          </div>
        ))}
      </div>
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
