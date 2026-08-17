"use client";

import React, { useState } from 'react';
import {
  Activity,
  Terminal,
  ShieldCheck,
  RotateCcw,
  Loader2,
  FileCode,
  Box,
  TestTube2,
  Play,
  Copy,
  Check,
  ListTodo,
} from 'lucide-react';
import { ExecutionGraph, ExecutionStage } from './ExecutionGraph';
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
  const [copiedDiff, setCopiedDiff] = useState(false);

  const repoName = connectedRepo?.fullName || 'Local Workspace';
  const branchName = connectedRepo?.selectedBranch || 'main';

  // Map backend trace events to 5-stage DAG
  const stages: ExecutionStage[] = [
    {
      id: 'onboarding',
      number: '01',
      name: 'MAPPER',
      role: 'AST Call Graph',
      status: displayData ? (displayData.nodes?.[0]?.status === 'completed' ? 'SUCCEEDED' : displayData.nodes?.[0]?.status === 'running' ? 'RUNNING' : 'QUEUED') : 'IDLE',
      duration: displayData?.nodes?.[0]?.duration || '--',
      cost: displayData?.nodes?.[0]?.cost || '--',
      model: 'Tree-Sitter AST',
      summary: 'Indexes repository files and resolves symbol proximity call graphs.',
    },
    {
      id: 'reproduction',
      number: '02',
      name: 'REPRO',
      role: 'Failing Test Synthesis',
      status: displayData ? (displayData.nodes?.[1]?.status === 'completed' ? 'SUCCEEDED' : displayData.nodes?.[1]?.status === 'running' ? 'RUNNING' : 'QUEUED') : 'IDLE',
      duration: displayData?.nodes?.[1]?.duration || '--',
      cost: displayData?.nodes?.[1]?.cost || '--',
      model: activeModel,
      summary: 'Synthesizes deterministic failing test suite validating the target bug (Red phase).',
    },
    {
      id: 'patcher',
      number: '03',
      name: 'PATCH',
      role: 'Surgical Modification',
      status: displayData ? (displayData.nodes?.[2]?.status === 'completed' ? 'SUCCEEDED' : displayData.nodes?.[2]?.status === 'running' ? 'RUNNING' : 'QUEUED') : 'IDLE',
      duration: displayData?.nodes?.[2]?.duration || '--',
      cost: displayData?.nodes?.[2]?.cost || '--',
      model: activeModel,
      summary: 'Generates unified code patch modifying only relevant AST subtrees.',
    },
    {
      id: 'verifier',
      number: '04',
      name: 'VERIFY',
      role: 'Sandbox Pytest Suite',
      status: displayData ? (displayData.nodes?.[3]?.status === 'completed' ? 'SUCCEEDED' : displayData.nodes?.[3]?.status === 'running' ? 'RUNNING' : 'QUEUED') : 'IDLE',
      duration: displayData?.nodes?.[3]?.duration || '--',
      cost: displayData?.nodes?.[3]?.cost || '--',
      model: 'Tier B Container',
      summary: 'Executes reproduction and full regression test suite inside isolated sandbox (Green phase).',
    },
    {
      id: 'reviewer',
      number: '05',
      name: 'REVIEW',
      role: 'Evidence Bundle Seal',
      status: displayData ? (displayData.nodes?.[4]?.status === 'completed' ? 'VERIFIED' : displayData.nodes?.[4]?.status === 'running' ? 'RUNNING' : 'QUEUED') : 'IDLE',
      duration: displayData?.nodes?.[4]?.duration || '--',
      cost: displayData?.nodes?.[4]?.cost || '--',
      model: 'Proof Layer Auditor',
      summary: 'Constructs SHA-256 hash chains across all artifacts and seals execution proof.',
    },
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
    <div className="flex-1 flex flex-col gap-5" id="tabpanel-overview" role="tabpanel">
      {/* 1. CLEAN HERO BANNER */}
      <div className="loom-card-elevated flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-mono font-bold text-[var(--brand-hover)] bg-[var(--brand-soft)] px-2 py-0.5 rounded border border-[var(--brand)]/30">
              CONTROL PLANE
            </span>
            <span className="text-xs font-mono text-[var(--text-muted)]">{repoName}</span>
          </div>
          <h2 className="text-base font-bold text-[var(--text-primary)] tracking-tight uppercase font-mono">
            Autonomous Engineering Control Plane
          </h2>
          <p className="text-xs text-[var(--text-secondary)] mt-0.5 max-w-2xl">
            Execute verified multi-agent DAG pipelines on <span className="text-[var(--text-primary)] font-mono font-semibold">{repoName}</span> with isolated sandboxes and cryptographic evidence bundles.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onOpenLiveBox}
            className="btn-primary h-8 px-3.5 text-xs gap-1.5"
          >
            <Play className="h-3 w-3 fill-current" />
            <span>Launch Run</span>
          </button>
          {githubIssues.length > 0 && onOpenIssuesDrawer && (
            <button
              onClick={onOpenIssuesDrawer}
              className="btn-secondary h-8 px-3 text-xs gap-1.5"
            >
              <ListTodo className="h-3.5 w-3.5 text-[var(--brand)]" />
              <span>Browse Issues ({githubIssues.length})</span>
            </button>
          )}
          {onOpenRepoModal && (
            <button
              onClick={onOpenRepoModal}
              className="btn-secondary h-8 px-3 text-xs gap-1.5"
            >
              <Box className="h-3.5 w-3.5 text-[var(--cyan)]" />
              <span>Repo Settings</span>
            </button>
          )}
        </div>
      </div>

      {/* 2. REAL-TIME USER REPOSITORY STATE STRIP */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono">
        <div className="loom-card p-3 flex items-center justify-between">
          <div className="min-w-0">
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-bold">CONNECTED REPO</p>
            <p className="text-xs font-bold text-[var(--text-primary)] mt-0.5 truncate" title={repoName}>
              {connectedRepo?.name || repoName}
            </p>
          </div>
          <div className="h-2 w-2 rounded-full bg-[var(--brand)] shrink-0" />
        </div>

        <div className="loom-card p-3 flex items-center justify-between">
          <div>
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-bold">ACTIVE BRANCH</p>
            <p className="text-xs font-bold text-[var(--cyan)] mt-0.5 font-mono">{branchName}</p>
          </div>
          <div className="h-2 w-2 rounded-full bg-[var(--cyan)]" />
        </div>

        <div className="loom-card p-3 flex items-center justify-between">
          <div>
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-bold">GITHUB ISSUES</p>
            <p className="text-base font-bold text-[var(--brand-hover)] mt-0.5">{githubIssues.length}</p>
          </div>
          <div className={`h-2 w-2 rounded-full ${githubIssues.length > 0 ? 'bg-[var(--brand)]' : 'bg-[var(--text-muted)]'}`} />
        </div>

        <div className="loom-card p-3 flex items-center justify-between">
          <div>
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-bold">EXECUTION STATE</p>
            <p className={`text-xs font-bold mt-0.5 ${displayData?.status === 'VERIFIED SUCCESS' ? 'text-[var(--success)]' : displayData ? 'text-[var(--cyan)]' : 'text-[var(--text-muted)]'}`}>
              {displayData ? displayData.status : 'STANDBY'}
            </p>
          </div>
          <div className={`h-2 w-2 rounded-full ${displayData ? 'bg-[var(--success)]' : 'bg-[var(--text-muted)]'}`} />
        </div>
      </div>

      {/* 3. 5-STAGE EXECUTION GRAPH */}
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

      {/* 4. ACTIVE RUN WORKSTATION & DETAILS */}
      {displayData ? (
        <div className="loom-card flex flex-col gap-4">
          {/* Run Header with Metadata */}
          <div className="flex items-start justify-between flex-wrap gap-3 pb-3 border-b border-[var(--border-subtle)]">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-mono font-bold text-[var(--brand)]">
                  {displayData.id}
                </span>
                <span className={`status-pill ${displayData.status === 'VERIFIED SUCCESS' ? 'status-pill-verified' : 'status-pill-running'} text-[9px] py-0`}>
                  {displayData.status}
                </span>
              </div>
              <h3 className="text-xs font-bold text-[var(--text-primary)] font-mono">
                {displayData.issue}
              </h3>
              <div className="flex items-center gap-3 text-[10px] font-mono text-[var(--text-muted)] mt-1.5 flex-wrap">
                <span>Model: <span className="text-[var(--text-secondary)]">{displayData.model || activeModel}</span></span>
                <span>•</span>
                <span>Repo: <span className="text-[var(--text-secondary)]">{repoName}</span></span>
                <span>•</span>
                <span>Branch: <span className="text-[var(--text-secondary)]">{branchName}</span></span>
                <span>•</span>
                <span>Duration: <span className="text-[var(--text-secondary)]">{displayData.duration}</span></span>
                <span>•</span>
                <span>Cost: <span className="text-[var(--success)]">{displayData.cost}</span></span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {onRollback && (
                <button
                  onClick={onRollback}
                  className="btn-secondary h-7 px-2.5 text-xs gap-1.5 text-[var(--danger)] hover:border-[var(--danger)]/50"
                  title="Rollback Workspace to Snapshot"
                >
                  <RotateCcw className="h-3 w-3" />
                  <span>Rollback</span>
                </button>
              )}
            </div>
          </div>

          {/* Subtabs Bar */}
          <div className="flex items-center gap-1 border-b border-[var(--border-subtle)] pb-2 overflow-x-auto">
            {[
              { id: 'overview' as const, label: 'Overview', icon: Activity },
              { id: 'diff' as const, label: 'Patch Diff', icon: FileCode },
              { id: 'tests' as const, label: 'Reproduction Tests', icon: TestTube2 },
              { id: 'sandbox' as const, label: 'Sandbox Tier', icon: Box },
              { id: 'evidence' as const, label: 'Evidence Bundle', icon: ShieldCheck },
            ].map(tab => {
              const Icon = tab.icon;
              const isActive = detailTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setDetailTab(tab.id)}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono transition ${
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

          {/* Subtab: Overview */}
          {detailTab === 'overview' && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg font-mono">
                  <p className="text-[10px] text-[var(--text-muted)] uppercase">Execution Time</p>
                  <p className="text-sm font-bold text-[var(--text-primary)] mt-0.5">{displayData.duration}</p>
                  <p className="text-[10px] text-[var(--text-muted)] mt-0.5">Recorded run duration</p>
                </div>

                <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg font-mono">
                  <p className="text-[10px] text-[var(--text-muted)] uppercase">Inference & Sandbox Cost</p>
                  <p className="text-sm font-bold text-[var(--success)] mt-0.5">{displayData.cost}</p>
                  <p className="text-[10px] text-[var(--text-muted)] mt-0.5">Tracked step attribution</p>
                </div>

                <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg font-mono">
                  <p className="text-[10px] text-[var(--text-muted)] uppercase">Verification Status</p>
                  <p className={`text-sm font-bold mt-0.5 ${displayData.status === 'VERIFIED SUCCESS' ? 'text-[var(--success)]' : 'text-[var(--cyan)]'}`}>
                    {displayData.status}
                  </p>
                  <p className="text-[10px] text-[var(--text-muted)] mt-0.5">Tied to {repoName}</p>
                </div>
              </div>

              {/* Stage-by-Stage Breakdown */}
              <div className="space-y-1.5">
                <h4 className="text-[11px] font-bold text-[var(--text-muted)] uppercase tracking-wider font-mono">
                  Stage Execution Breakdown
                </h4>
                {stages.map((stage) => (
                  <div
                    key={stage.id}
                    className="p-2.5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg flex items-center justify-between gap-3 text-xs"
                  >
                    <div className="flex items-center gap-2.5">
                      <span className="font-mono text-[9px] font-bold text-[var(--brand)] bg-[var(--brand-soft)] px-1.5 py-0.5 rounded">
                        {stage.number}
                      </span>
                      <div>
                        <p className="font-bold text-[var(--text-primary)] font-mono text-xs">{stage.name}</p>
                        <p className="text-[10px] text-[var(--text-muted)]">{stage.role}</p>
                      </div>
                    </div>

                    <div className="flex items-center gap-3 font-mono text-[10px]">
                      <span className="text-[var(--text-secondary)]">{stage.duration}</span>
                      <span className="text-[var(--text-muted)]">{stage.cost}</span>
                      <span className={`${stage.status === 'SUCCEEDED' || stage.status === 'VERIFIED' ? 'text-[var(--success)]' : 'text-[var(--text-muted)]'} font-bold`}>
                        {stage.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Subtab: Diff */}
          {detailTab === 'diff' && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs font-mono text-[var(--text-muted)]">
                <span>VERIFIED SURGICAL DIFF</span>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(displayData.patchDiff);
                    setCopiedDiff(true);
                    setTimeout(() => setCopiedDiff(false), 2000);
                  }}
                  className="btn-secondary h-6 px-2 text-[10px] gap-1"
                >
                  {copiedDiff ? <Check className="h-3 w-3 text-[var(--success)]" /> : <Copy className="h-3 w-3" />}
                  <span>{copiedDiff ? 'Copied' : 'Copy Diff'}</span>
                </button>
              </div>
              <div className="bg-[var(--bg-root)] border border-[var(--border-subtle)] rounded-xl p-3.5 font-mono text-xs text-[var(--text-secondary)] overflow-x-auto space-y-1 max-h-96">
                {displayData.patchDiff ? (
                  <pre className="whitespace-pre-wrap">{displayData.patchDiff}</pre>
                ) : (
                  <p className="text-[var(--text-muted)] italic">No patch diff generated for this run.</p>
                )}
              </div>
            </div>
          )}

          {/* Subtab: Tests */}
          {detailTab === 'tests' && (
            <div className="space-y-3">
              <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-[var(--text-primary)] font-mono">REPRODUCTION TEST CASE (RED ➔ GREEN)</span>
                  <span className={`status-pill ${displayData.status === 'VERIFIED SUCCESS' ? 'status-pill-verified' : 'status-pill-running'} text-[9px] py-0`}>
                    {displayData.status === 'VERIFIED SUCCESS' ? 'PASSED' : 'EXECUTED'}
                  </span>
                </div>
                <div className="bg-[var(--bg-root)] border border-[var(--border-subtle)] rounded-lg p-3 font-mono text-xs text-[var(--text-secondary)] overflow-x-auto">
                  {displayData.reproductionTest ? (
                    <pre className="whitespace-pre-wrap text-[var(--brand-hover)]">{displayData.reproductionTest}</pre>
                  ) : (
                    <p className="text-[var(--text-muted)] italic">No reproduction test script recorded for this run.</p>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Subtab: Sandbox */}
          {detailTab === 'sandbox' && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 font-mono">
              <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                <p className="text-[10px] text-[var(--text-muted)] uppercase font-bold">ISOLATION TIER</p>
                <p className="text-sm font-bold text-[var(--cyan)] mt-0.5">Tier B (Container)</p>
                <p className="text-[10px] text-[var(--text-muted)] mt-0.5">gVisor Sandbox Isolation</p>
              </div>

              <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                <p className="text-[10px] text-[var(--text-muted)] uppercase font-bold">EGRESS RESTRICTIONS</p>
                <p className="text-sm font-bold text-[var(--success)] mt-0.5">DENY_ALL</p>
                <p className="text-[10px] text-[var(--text-muted)] mt-0.5">Strict egress firewall active</p>
              </div>

              <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                <p className="text-[10px] text-[var(--text-muted)] uppercase font-bold">TARGET ENVIRONMENT</p>
                <p className="text-sm font-bold text-[var(--text-primary)] mt-0.5 truncate">{repoName}</p>
                <p className="text-[10px] text-[var(--text-muted)] mt-0.5">{branchName}</p>
              </div>
            </div>
          )}

          {/* Subtab: Evidence Proof Layer */}
          {detailTab === 'evidence' && (
            <EvidenceView displayData={displayData} runId={displayData.id} connectedRepoName={repoName} onOpenLiveBox={onOpenLiveBox} />
          )}
        </div>
      ) : (
        <div className="loom-card flex flex-col items-center justify-center text-center py-10 px-4 gap-3">
          <div className="h-10 w-10 rounded-xl bg-[var(--brand-soft)] border border-[var(--brand)]/30 flex items-center justify-center text-[var(--brand)]">
            <Activity className="h-5 w-5" />
          </div>
          <div className="max-w-md space-y-1">
            <h3 className="text-sm font-bold text-[var(--text-primary)] font-mono">
              Workstation Ready for {repoName}
            </h3>
            <p className="text-xs text-[var(--text-muted)]">
              Select an existing run from the history sidebar or launch a new issue execution to start the multi-agent DAG pipeline.
            </p>
          </div>
          <button
            onClick={onOpenLiveBox}
            className="btn-primary h-8 px-4 text-xs gap-1.5 mt-1"
          >
            <Play className="h-3 w-3 fill-current" />
            <span>Launch Issue Run</span>
          </button>
        </div>
      )}

      {/* 5. USER REPOSITORY ISSUES & QUICK ACTIONS */}
      {githubIssues.length > 0 ? (
        <div className="loom-card space-y-2.5">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider font-mono">
              Open Issues in {connectedRepo?.name || repoName}
            </h3>
            {onOpenIssuesDrawer && (
              <button
                onClick={onOpenIssuesDrawer}
                className="text-[11px] font-mono text-[var(--brand-hover)] hover:underline"
              >
                View all ({githubIssues.length}) →
              </button>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2.5">
            {githubIssues.slice(0, 4).map((issue) => (
              <button
                key={issue.number}
                onClick={() => onSelectStarterIssue?.(`#${issue.number}: ${issue.title}\n\n${issue.body || ''}`)}
                className="p-2.5 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border-subtle)] hover:border-[var(--brand)] hover:bg-[var(--bg-hover)] text-left transition flex items-center gap-2 group"
              >
                <span className="text-xs font-mono font-bold text-[var(--brand)] shrink-0">#{issue.number}</span>
                <div className="min-w-0 flex-1">
                  <h4 className="text-xs font-medium text-[var(--text-primary)] group-hover:text-[var(--brand-hover)] transition truncate">
                    {issue.title}
                  </h4>
                </div>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="loom-card space-y-2.5">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider font-mono">
              Quick Actions for {connectedRepo?.name || repoName}
            </h3>
            <span className="text-[10px] font-mono text-[var(--text-muted)]">1-Click Launch</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
            {[
              { title: 'Run Full Test Suite', prompt: 'Execute the full test suite and verify no regressions in the workspace' },
              { title: 'Fix Type Errors & Lints', prompt: 'Analyze codebase for type errors and linter issues, then synthesize fixes' },
              { title: 'Security Audit & SAST', prompt: 'Run static analysis and check for credential or secret exposures in diff' },
            ].map((action, idx) => (
              <button
                key={idx}
                onClick={() => onSelectStarterIssue?.(action.prompt)}
                className="p-2.5 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border-subtle)] hover:border-[var(--brand)] hover:bg-[var(--bg-hover)] text-left transition flex items-center gap-2 group"
              >
                <span className="text-xs font-mono font-bold text-[var(--brand)] shrink-0">⚡</span>
                <div className="min-w-0 flex-1">
                  <h4 className="text-xs font-medium text-[var(--text-primary)] group-hover:text-[var(--brand-hover)] transition truncate font-mono">
                    {action.title}
                  </h4>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};