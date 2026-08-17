"use client";

import React, { useState } from 'react';
import Link from 'next/link';
import {
  Activity,
  Terminal,
  ShieldCheck,
  Clock,
  DollarSign,
  RotateCcw,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertTriangle,
  ChevronRight,
  Sparkles,
  Zap,
  Cpu,
  GitBranch,
  Layers,
  ArrowRight,
  FolderGit2,
  ExternalLink,
  MessageSquare,
  ListTodo,
  FileCode,
  Box,
  TestTube2,
  Play,
  Copy,
  Check,
} from 'lucide-react';
import { ExecutionGraph, ExecutionStage, StageState } from './ExecutionGraph';
import { EvidenceView } from './EvidenceView';
import { ConnectedRepoState, GitHubIssue } from '../hooks/useGitHub';

interface OverviewTabProps {
  displayData: any;
  selectedRun: string | null;
  onRollback: () => void;
  isLoadingDetails: boolean;
  onOpenLiveBox?: () => void;
  onSelectStarterIssue?: (issue: string) => void;
  activeModel?: string;
  connectedRepo?: ConnectedRepoState | null;
  githubIssues?: GitHubIssue[];
  onOpenRepoModal?: () => void;
  onOpenIssuesDrawer?: () => void;
}

const STARTER_TASKS = [
  {
    icon: '⚡',
    title: 'OAuth State Replay Guard',
    issue: 'Implement cryptographic state verification for OAuth redirects',
    desc: 'Prevents cross-origin token replays and forgery',
  },
  {
    icon: '🛡️',
    title: 'Context Manager Budget Estimator',
    issue: 'Fix token budget estimation edge case in context manager',
    desc: 'Prevents AST graph truncation on large repositories',
  },
  {
    icon: '📈',
    title: 'AST Symbol Dependency Indexer',
    issue: 'Optimize AST call graph dependency indexer for Python & TypeScript',
    desc: 'Enhances Tree-Sitter symbol resolution speed',
  },
  {
    icon: '🧪',
    title: 'Sandbox Egress Isolation Suite',
    issue: 'Synthesize regression test suite for sandbox tier guards',
    desc: 'Verifies network egress filtering on Tier B containers',
  },
];

export const OverviewTab: React.FC<OverviewTabProps> = ({
  displayData,
  selectedRun,
  onRollback,
  isLoadingDetails,
  onOpenLiveBox,
  onSelectStarterIssue,
  activeModel = 'claude-3-7-sonnet',
  connectedRepo,
  githubIssues = [],
  onOpenRepoModal,
  onOpenIssuesDrawer,
}) => {
  const [detailTab, setDetailTab] = useState<'overview' | 'logs' | 'diff' | 'tests' | 'sandbox' | 'evidence'>('overview');
  const [activeStageId, setActiveStageId] = useState<string | null>(null);

  // Map backend trace events to 5-stage DAG
  const stages: ExecutionStage[] = [
    {
      id: 'onboarding',
      number: '01',
      name: 'MAPPER',
      role: 'AST Call Graph',
      status: displayData ? (displayData.nodes?.[0]?.status === 'completed' ? 'SUCCEEDED' : displayData.nodes?.[0]?.status === 'running' ? 'RUNNING' : 'QUEUED') : 'SUCCEEDED',
      duration: displayData?.nodes?.[0]?.duration || '12.4s',
      cost: displayData?.nodes?.[0]?.cost || '$0.0003',
    },
    {
      id: 'reproduction',
      number: '02',
      name: 'REPRO',
      role: 'Failing Test Synthesis',
      status: displayData ? (displayData.nodes?.[1]?.status === 'completed' ? 'SUCCEEDED' : displayData.nodes?.[1]?.status === 'running' ? 'RUNNING' : 'QUEUED') : 'SUCCEEDED',
      duration: displayData?.nodes?.[1]?.duration || '31.2s',
      cost: displayData?.nodes?.[1]?.cost || '$0.0008',
    },
    {
      id: 'patcher',
      number: '03',
      name: 'PATCH',
      role: 'Surgical Modification',
      status: displayData ? (displayData.nodes?.[2]?.status === 'completed' ? 'SUCCEEDED' : displayData.nodes?.[2]?.status === 'running' ? 'RUNNING' : 'QUEUED') : 'SUCCEEDED',
      duration: displayData?.nodes?.[2]?.duration || '18.7s',
      cost: displayData?.nodes?.[2]?.cost || '$0.0025',
    },
    {
      id: 'verifier',
      number: '04',
      name: 'VERIFY',
      role: 'Sandbox Pytest Suite',
      status: displayData ? (displayData.nodes?.[3]?.status === 'completed' ? 'SUCCEEDED' : displayData.nodes?.[3]?.status === 'running' ? 'RUNNING' : 'QUEUED') : 'SUCCEEDED',
      duration: displayData?.nodes?.[3]?.duration || '9.1s',
      cost: displayData?.nodes?.[3]?.cost || '$0.0002',
    },
    {
      id: 'reviewer',
      number: '05',
      name: 'REVIEW',
      role: 'Evidence Bundle Seal',
      status: displayData ? (displayData.nodes?.[4]?.status === 'completed' ? 'SUCCEEDED' : displayData.nodes?.[4]?.status === 'running' ? 'RUNNING' : 'QUEUED') : 'VERIFIED',
      duration: displayData?.nodes?.[4]?.duration || '4.3s',
      cost: displayData?.nodes?.[4]?.cost || '$0.0003',
    },
  ];

  const sampleLogs = [
    { time: '18:42:04', step: 'MAPPER', message: 'Repository indexed: 284 source files analyzed via Tree-Sitter AST' },
    { time: '18:42:08', step: 'MAPPER', message: 'Symbol proximity call graph generated (1,492 tokens budget)' },
    { time: '18:42:11', step: 'REPRO', message: 'Synthesizing reproduction test asserting target vulnerability (Red phase)' },
    { time: '18:42:25', step: 'REPRO', message: 'Reproduction test verified failing in sandbox: pytest tests/repro_test.py (FAILED)' },
    { time: '18:42:29', step: 'PATCH', message: 'Patcher agent synthesized unified diff across 2 impacted source modules' },
    { time: '18:42:37', step: 'VERIFY', message: 'Running test harness in isolated container: 48 passed, 0 failed (Green phase)' },
    { time: '18:42:41', step: 'REVIEW', message: 'Computing cryptographic SHA-256 hash chains for evidence artifacts' },
    { time: '18:42:43', step: 'REVIEW', message: 'Evidence bundle verified and sealed with root hash: ef2d127de37b942b' },
  ];

  if (isLoadingDetails) {
    return (
      <div className="flex-1 loom-card flex items-center justify-center gap-3 text-[var(--text-muted)] min-h-[400px]">
        <Loader2 className="h-5 w-5 animate-spin text-[var(--brand)]" />
        <span className="text-xs font-mono">Loading harness execution details...</span>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col gap-6" id="tabpanel-overview" role="tabpanel">
      {/* 1. AUTONOMOUS ENGINEERING CONTROL PLANE HEADER */}
      <div className="loom-card-elevated flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-mono font-bold text-[var(--brand-hover)] bg-[var(--brand-soft)] px-2 py-0.5 rounded border border-[var(--brand)]/30">
              CONTROL PLANE
            </span>
            <span className="text-xs font-mono text-[var(--text-muted)]">v2.4.0</span>
          </div>
          <h2 className="text-lg font-bold text-[var(--text-primary)] tracking-tight uppercase font-mono">
            Autonomous Engineering Control Plane
          </h2>
          <p className="text-xs text-[var(--text-secondary)] mt-0.5 max-w-2xl">
            Solve software issues through a verified multi-agent execution pipeline with isolated sandboxes and cryptographic evidence bundles.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={onOpenLiveBox}
            className="btn-primary gap-1.5"
          >
            <Play className="h-3.5 w-3.5 fill-current" />
            <span>New Run</span>
          </button>
          {onOpenIssuesDrawer && (
            <button
              onClick={onOpenIssuesDrawer}
              className="btn-secondary gap-1.5"
            >
              <ListTodo className="h-3.5 w-3.5 text-[var(--brand)]" />
              <span>Browse Issues ({githubIssues.length})</span>
            </button>
          )}
        </div>
      </div>

      {/* 2. SYSTEM STATE STRIP */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono">
        <div className="loom-card p-3.5 flex items-center justify-between">
          <div>
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-bold">ACTIVE RUNS</p>
            <p className="text-lg font-bold text-[var(--cyan)] mt-0.5">03</p>
          </div>
          <div className="h-2 w-2 rounded-full bg-[var(--cyan)] animate-pulse" />
        </div>

        <div className="loom-card p-3.5 flex items-center justify-between">
          <div>
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-bold">QUEUED</p>
            <p className="text-lg font-bold text-[var(--text-secondary)] mt-0.5">02</p>
          </div>
          <div className="h-2 w-2 rounded-full bg-[var(--text-muted)]" />
        </div>

        <div className="loom-card p-3.5 flex items-center justify-between">
          <div>
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-bold">VERIFIED</p>
            <p className="text-lg font-bold text-[var(--success)] mt-0.5">187</p>
          </div>
          <div className="h-2 w-2 rounded-full bg-[var(--success)]" />
        </div>

        <div className="loom-card p-3.5 flex items-center justify-between">
          <div>
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-bold">FAILED</p>
            <p className="text-lg font-bold text-[var(--danger)] mt-0.5">04</p>
          </div>
          <div className="h-2 w-2 rounded-full bg-[var(--danger)]" />
        </div>
      </div>

      {/* 3. SIGNATURE COMPONENT: 5-STAGE CONNECTED EXECUTION GRAPH */}
      <div className="loom-card">
        <ExecutionGraph
          stages={stages}
          activeStageId={activeStageId}
          onSelectStage={(id) => {
            setActiveStageId(id);
            if (id === 'reviewer') setDetailTab('evidence');
            else if (id === 'patcher') setDetailTab('diff');
            else if (id === 'verifier' || id === 'reproduction') setDetailTab('tests');
            else setDetailTab('overview');
          }}
        />
      </div>

      {/* 4. EXECUTION DETAILS & TABBED WORKSPACE */}
      <div className="loom-card flex flex-col gap-4">
        {/* Run Header with Metadata */}
        <div className="flex items-start justify-between flex-wrap gap-3 pb-4 border-b border-[var(--border-subtle)]">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-mono font-bold text-[var(--brand)]">
                {displayData?.id || selectedRun || 'RUN #00427'}
              </span>
              <span className="status-pill status-pill-verified text-[10px]">
                {displayData?.status || 'VERIFIED SUCCESS'}
              </span>
            </div>
            <h3 className="text-sm font-bold text-[var(--text-primary)] font-sans">
              {displayData?.issue || 'Fix OAuth state verification replay vulnerability across auth endpoints'}
            </h3>
            <div className="flex items-center gap-3 text-[11px] font-mono text-[var(--text-muted)] mt-1.5 flex-wrap">
              <span>Model: <span className="text-[var(--text-secondary)]">{displayData?.model || activeModel}</span></span>
              <span>•</span>
              <span>Repo: <span className="text-[var(--text-secondary)]">{connectedRepo?.fullName || 'Loom-Unified-Agentic'}</span></span>
              <span>•</span>
              <span>Branch: <span className="text-[var(--text-secondary)]">{connectedRepo?.selectedBranch || 'main'}</span></span>
              <span>•</span>
              <span>Duration: <span className="text-[var(--text-secondary)]">{displayData?.duration || '31.2s'}</span></span>
              <span>•</span>
              <span>Cost: <span className="text-[var(--text-secondary)]">{displayData?.cost || '$0.0038'}</span></span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {onRollback && (
              <button
                onClick={onRollback}
                className="btn-secondary h-8 text-xs gap-1.5 text-[var(--danger)] hover:border-[var(--danger)]/50"
                title="Rollback Workspace to Snapshot"
              >
                <RotateCcw className="h-3 w-3" />
                <span>Rollback</span>
              </button>
            )}
          </div>
        </div>

        {/* Execution Details Subtabs */}
        <div className="flex items-center gap-1 border-b border-[var(--border-subtle)] pb-2 overflow-x-auto">
          {[
            { id: 'overview' as const, label: 'Overview', icon: Activity },
            { id: 'logs' as const, label: 'Logs', icon: Terminal },
            { id: 'diff' as const, label: 'Diff', icon: FileCode },
            { id: 'tests' as const, label: 'Tests', icon: TestTube2 },
            { id: 'sandbox' as const, label: 'Sandbox', icon: Box },
            { id: 'evidence' as const, label: 'Evidence', icon: ShieldCheck },
          ].map(tab => {
            const Icon = tab.icon;
            const isActive = detailTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setDetailTab(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition ${
                  isActive
                    ? 'bg-[var(--brand-soft)] text-[var(--brand-hover)] border border-[var(--brand)]/30 font-semibold'
                    : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] border border-transparent'
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Subtab 1: Overview */}
        {detailTab === 'overview' && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="p-3.5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                <p className="text-[10px] font-mono text-[var(--text-muted)] uppercase">Total Execution Time</p>
                <p className="text-base font-bold font-mono text-[var(--text-primary)] mt-1">{displayData?.duration || '31.2s'}</p>
                <p className="text-[11px] text-[var(--text-muted)] mt-0.5">5 DAG stages completed</p>
              </div>

              <div className="p-3.5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                <p className="text-[10px] font-mono text-[var(--text-muted)] uppercase">Inference & Sandbox Cost</p>
                <p className="text-base font-bold font-mono text-[var(--success)] mt-1">{displayData?.cost || '$0.0038'}</p>
                <p className="text-[11px] text-[var(--text-muted)] mt-0.5">Under $0.05 budget ceiling</p>
              </div>

              <div className="p-3.5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                <p className="text-[10px] font-mono text-[var(--text-muted)] uppercase">Evidence Chain Status</p>
                <p className="text-base font-bold font-mono text-[var(--brand)] mt-1">SEALED (SHA-256)</p>
                <p className="text-[11px] text-[var(--text-muted)] mt-0.5">5 verified artifacts committed</p>
              </div>
            </div>

            {/* Stage-by-Stage Telemetry Details */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider font-mono">
                Stage Execution Breakdown
              </h4>
              {stages.map((stage) => (
                <div
                  key={stage.id}
                  className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg flex items-center justify-between gap-3 text-xs"
                >
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-[10px] font-bold text-[var(--brand)] bg-[var(--brand-soft)] px-1.5 py-0.5 rounded">
                      {stage.number}
                    </span>
                    <div>
                      <p className="font-bold text-[var(--text-primary)] font-mono">{stage.name}</p>
                      <p className="text-[11px] text-[var(--text-muted)]">{stage.role}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 font-mono text-[11px]">
                    <span className="text-[var(--text-secondary)]">{stage.duration}</span>
                    <span className="text-[var(--text-muted)]">{stage.cost}</span>
                    <span className="text-[var(--success)] font-bold">{stage.status}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Subtab 2: Logs */}
        {detailTab === 'logs' && (
          <div className="bg-[var(--bg-root)] border border-[var(--border-subtle)] rounded-xl p-4 font-mono text-xs text-[var(--text-secondary)] overflow-x-auto space-y-1.5 max-h-96">
            <div className="text-[10px] text-[var(--text-muted)] pb-2 border-b border-[var(--border-subtle)] flex items-center justify-between">
              <span>LIVE OUTPUT LOG STREAM</span>
              <span>8 EVENTS RECORDED</span>
            </div>
            {sampleLogs.map((log, i) => (
              <div key={i} className="flex items-start gap-3 leading-relaxed hover:bg-[var(--bg-hover)] p-1 rounded transition">
                <span className="text-[var(--text-muted)] select-none shrink-0">[{log.time}]</span>
                <span className="text-[var(--brand)] font-bold select-none shrink-0 w-16">[{log.step}]</span>
                <span className="text-[var(--text-primary)]">{log.message}</span>
              </div>
            ))}
          </div>
        )}

        {/* Subtab 3: Diff */}
        {detailTab === 'diff' && (
          <div className="space-y-3">
            <div className="flex items-center justify-between text-xs font-mono text-[var(--text-muted)]">
              <span>PATCH DIFF: loom/core/auth_handler.py</span>
              <span className="text-[var(--success)]">+12 lines / -4 lines</span>
            </div>
            <div className="bg-[var(--bg-root)] border border-[var(--border-subtle)] rounded-xl p-4 font-mono text-xs text-[var(--text-secondary)] overflow-x-auto space-y-1">
              <pre className="text-[var(--text-muted)]">--- a/loom/core/auth_handler.py</pre>
              <pre className="text-[var(--text-muted)]">+++ b/loom/core/auth_handler.py</pre>
              <pre className="text-[var(--brand)] font-bold">@@ -42,8 +42,16 @@ def verify_oauth_callback(code: str, state: str) -&gt; AuthToken:</pre>
              <pre className="text-[var(--text-secondary)]">     if not code or not state:</pre>
              <pre className="text-[var(--danger)] bg-[var(--danger)]/10 px-1 rounded">-        logger.warning(&quot;Missing oauth parameters&quot;)</pre>
              <pre className="text-[var(--danger)] bg-[var(--danger)]/10 px-1 rounded">-        raise OAuthValidationError(&quot;Invalid callback params&quot;)</pre>
              <pre className="text-[var(--success)] bg-[var(--success)]/10 px-1 rounded">+        # Fix: Enforce cryptographic state nonce validation</pre>
              <pre className="text-[var(--success)] bg-[var(--success)]/10 px-1 rounded">+        expected_nonce = session_store.pop_oauth_nonce(state)</pre>
              <pre className="text-[var(--success)] bg-[var(--success)]/10 px-1 rounded">+        if not expected_nonce or not hmac.compare_digest(expected_nonce, state):</pre>
              <pre className="text-[var(--success)] bg-[var(--success)]/10 px-1 rounded">+            logger.error(&quot;State verification failed: potential replay attack&quot;)</pre>
              <pre className="text-[var(--success)] bg-[var(--success)]/10 px-1 rounded">+            raise OAuthReplayError(&quot;Invalid or replayed state nonce&quot;)</pre>
              <pre className="text-[var(--text-secondary)]">     return token_service.exchange_code(code)</pre>
            </div>
          </div>
        )}

        {/* Subtab 4: Tests */}
        {detailTab === 'tests' && (
          <div className="space-y-4">
            <div className="p-3.5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold text-[var(--text-primary)] font-mono">REPRODUCTION TEST SUITE</span>
                <span className="status-pill status-pill-verified text-[10px]">PASSING</span>
              </div>
              <div className="bg-[var(--bg-root)] border border-[var(--border-subtle)] rounded-lg p-3 font-mono text-xs text-[var(--text-secondary)] overflow-x-auto">
                <pre className="text-[var(--brand)]">def test_oauth_state_replay_reproduction():</pre>
                <pre className="text-[var(--text-secondary)]">    &quot;&quot;&quot;Verify resolution for OAuth state replay vulnerability&quot;&quot;&quot;</pre>
                <pre className="text-[var(--text-secondary)]">    client = OAuthTestClient()</pre>
                <pre className="text-[var(--text-secondary)]">    state_nonce = client.generate_nonce()</pre>
                <pre className="text-[var(--text-secondary)]">    # First exchange succeeds</pre>
                <pre className="text-[var(--text-secondary)]">    res1 = client.exchange_callback(code=&quot;auth_code_1&quot;, state=state_nonce)</pre>
                <pre className="text-[var(--text-secondary)]">    assert res1.status_code == 200</pre>
                <pre className="text-[var(--text-secondary)]">    # Second exchange with same state nonce must fail (replay protection)</pre>
                <pre className="text-[var(--text-secondary)]">    with pytest.raises(OAuthReplayError):</pre>
                <pre className="text-[var(--text-secondary)]">        client.exchange_callback(code=&quot;auth_code_2&quot;, state=state_nonce)</pre>
              </div>
            </div>
          </div>
        )}

        {/* Subtab 5: Sandbox */}
        {detailTab === 'sandbox' && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 font-mono">
              <div className="p-3.5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                <p className="text-[10px] text-[var(--text-muted)] uppercase font-bold">ISOLATION TIER</p>
                <p className="text-base font-bold text-[var(--cyan)] mt-1">Tier B (Container)</p>
                <p className="text-[11px] text-[var(--text-muted)] mt-0.5">gVisor Sandbox Isolation</p>
              </div>

              <div className="p-3.5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                <p className="text-[10px] text-[var(--text-muted)] uppercase font-bold">EGRESS RESTRICTIONS</p>
                <p className="text-base font-bold text-[var(--success)] mt-1">DENY_ALL</p>
                <p className="text-[11px] text-[var(--text-muted)] mt-0.5">No outbound network access</p>
              </div>

              <div className="p-3.5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                <p className="text-[10px] text-[var(--text-muted)] uppercase font-bold">RESOURCE BUDGET</p>
                <p className="text-base font-bold text-[var(--text-primary)] mt-1">2 vCPU / 4 GB</p>
                <p className="text-[11px] text-[var(--text-muted)] mt-0.5">Peak memory: 342 MB</p>
              </div>
            </div>
          </div>
        )}

        {/* Subtab 6: Evidence Proof Layer */}
        {detailTab === 'evidence' && (
          <EvidenceView runId={displayData?.id || selectedRun || 'run_427'} />
        )}
      </div>

      {/* 5. 1-CLICK ISSUE RUNNER / STARTERS */}
      <div className="loom-card">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider font-mono">
              1-Click Engineering Tasks
            </h3>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              Launch autonomous runs immediately with predefined issue specs
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {STARTER_TASKS.map((task, idx) => (
            <button
              key={idx}
              onClick={() => onSelectStarterIssue?.(task.issue)}
              className="p-3.5 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-subtle)] hover:border-[var(--border-default)] hover:bg-[var(--bg-hover)] text-left transition flex items-start gap-3 group"
            >
              <span className="text-xl p-2 rounded-lg bg-[var(--bg-surface)] border border-[var(--border-subtle)] group-hover:scale-105 transition shrink-0">
                {task.icon}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-[var(--text-primary)] group-hover:text-[var(--brand-hover)] transition">
                    {task.title}
                  </h4>
                  <span className="btn-tertiary text-[11px] p-0">
                    Run →
                  </span>
                </div>
                <p className="text-xs text-[var(--text-secondary)] font-mono mt-0.5 truncate">
                  {task.issue}
                </p>
                <p className="text-[11px] text-[var(--text-muted)] mt-1">
                  {task.desc}
                </p>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};