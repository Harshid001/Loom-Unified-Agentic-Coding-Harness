"use client";

import React, { useState, useCallback } from 'react';
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
  AlertTriangle,
  CheckCircle2,
  GitBranch,
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
  const [rollbackArmed, setRollbackArmed] = useState(false);

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
      role: 'Proof & Fix Synthesis',
      status: displayData ? (displayData.nodes?.[4]?.status === 'completed' ? 'VERIFIED' : displayData.nodes?.[4]?.status === 'running' ? 'RUNNING' : 'QUEUED') : 'IDLE',
      duration: displayData?.nodes?.[4]?.duration || '--',
      cost: displayData?.nodes?.[4]?.cost || '--',
      model: 'Proof Layer Auditor',
      summary: 'Synthesizes plain-language resolution brief, constructs SHA-256 hash chains across artifacts, and seals execution proof.',
    },
  ];

  const handleRollbackClick = useCallback(() => {
    if (!rollbackArmed || !onRollback) return;
    onRollback();
    setRollbackArmed(false);
  }, [rollbackArmed, onRollback]);

  if (isLoadingDetails) {
    return (
      <div className="flex-1 loom-card flex items-center justify-center gap-3 text-[var(--text-muted)] min-h-[400px]">
        <Loader2 className="h-5 w-5 animate-spin text-[var(--brand)]" />
        <span className="text-xs font-mono">Loading harness execution details…</span>
      </div>
    );
  }

  const subtabs: { id: typeof detailTab; label: string; icon: any }[] = [
    { id: 'overview', label: 'Overview', icon: Activity },
    { id: 'diff', label: 'Patch Diff', icon: FileCode },
    { id: 'tests', label: 'Tests', icon: TestTube2 },
    { id: 'sandbox', label: 'Sandbox Tier', icon: Box },
    { id: 'evidence', label: 'Evidence', icon: ShieldCheck },
  ];

  return (
    <div className="flex-1 flex flex-col gap-5" id="tabpanel-overview" role="tabpanel">
      {/* ── 1. HERO BANNER ── */}
      <div className="loom-card-elevated overflow-hidden relative">
        {/* Subtle brand gradient accent at top */}
        <div className="absolute top-0 inset-x-0 h-[1px] bg-gradient-to-r from-transparent via-[var(--brand)]/50 to-transparent" aria-hidden="true" />
        {/* Background ambient glow */}
        <div className="absolute top-0 right-0 w-64 h-64 bg-[var(--brand)]/5 rounded-full blur-[80px] pointer-events-none" aria-hidden="true" />
        <div className="relative z-10 flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] font-mono font-bold text-[var(--brand-hover)] bg-[var(--brand-soft)] px-2 py-0.5 rounded border border-[var(--brand)]/30">
                CONTROL PLANE
              </span>
              {!displayData && (
                <span className="text-[10px] font-mono text-[var(--text-muted)] bg-[var(--bg-surface)] px-2 py-0.5 rounded border border-[var(--border-subtle)]">
                  {repoName}
                </span>
              )}
            </div>
            <h2 className="text-base font-bold text-[var(--text-primary)] tracking-tight font-mono">
              {displayData ? 'Run Workstation' : 'Autonomous Engineering Control Plane'}
            </h2>
            <p className="text-xs text-[var(--text-secondary)] mt-1 max-w-2xl leading-relaxed">
              {displayData
                ? `Inspecting execution run ${displayData.id} on ${repoName} · branch ${branchName}`
                : `Execute verified multi-agent DAG pipelines on ${repoName} with isolated sandboxes and cryptographic evidence bundles.`
              }
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={onOpenLiveBox}
              className="btn-primary h-8 px-3.5 text-xs gap-1.5"
            >
              <Play className="h-3 w-3 fill-current relative z-10" />
              <span className="relative z-10">Launch Run</span>
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
      </div>

      {/* ── 2. READY HERO (no run selected) ── */}
      {!displayData && (
        <div className="space-y-5">
          {/* Animated Mini-DAG Pipeline */}
          <div className="loom-card relative overflow-hidden">
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-80 h-80 bg-[var(--brand)]/6 rounded-full blur-[100px] pointer-events-none" aria-hidden="true" />
            <div className="relative z-10">
              <div className="text-center mb-6">
                <div className="sha-seal h-16 w-16 rounded-full mx-auto mb-4 animate-float">
                  <div className="h-16 w-16 rounded-full bg-[var(--bg-surface)] flex items-center justify-center">
                    <Activity className="h-7 w-7 text-[var(--brand)]" />
                  </div>
                </div>
                <h3 className="text-lg font-bold text-[var(--text-primary)] font-mono mb-1">
                  Verification Engine Ready
                </h3>
                <p className="text-xs text-[var(--text-secondary)] max-w-md mx-auto leading-relaxed">
                  Launch a multi-agent DAG pipeline to autonomously diagnose, patch, and verify code changes with SHA-256 hash-chain proof bundles.
                </p>
              </div>

              {/* 5-Stage Mini Pipeline */}
              <div className="flex items-center justify-center gap-1 mb-6 overflow-x-auto pb-2">
                {[
                  { num: '01', name: 'MAPPER', color: 'var(--brand)' },
                  { num: '02', name: 'REPRO', color: 'var(--cyan)' },
                  { num: '03', name: 'PATCH', color: 'var(--brand-hover)' },
                  { num: '04', name: 'VERIFY', color: 'var(--success)' },
                  { num: '05', name: 'REVIEW', color: 'var(--warning)' },
                ].map((stage, i, arr) => (
                  <React.Fragment key={stage.num}>
                    <div className="empty-state-stage flex flex-col items-center gap-1.5 px-2 py-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] min-w-[72px]">
                      <span className="text-[9px] font-mono font-bold" style={{ color: stage.color }}>
                        {stage.num}
                      </span>
                      <span className="text-[10px] font-mono font-bold text-[var(--text-primary)]">
                        {stage.name}
                      </span>
                      <div className="h-1.5 w-1.5 rounded-full bg-[var(--text-muted)]" />
                    </div>
                    {i < arr.length - 1 && (
                      <div className="text-[var(--border-default)] shrink-0" aria-hidden="true">
                        <svg width="16" height="8" viewBox="0 0 16 8"><path d="M0 4h12M10 1l3 3-3 3" stroke="currentColor" strokeWidth="1.5" fill="none" /></svg>
                      </div>
                    )}
                  </React.Fragment>
                ))}
              </div>

              {/* CTA */}
              <div className="flex flex-col items-center gap-3">
                <button
                  onClick={onOpenLiveBox}
                  className="btn-primary h-10 px-6 text-sm gap-2 shadow-lg shadow-[var(--brand)]/25"
                >
                  <Play className="h-4 w-4 fill-current relative z-10" />
                  <span className="relative z-10">Launch Issue Run</span>
                </button>
                <div className="flex items-center gap-2 flex-wrap justify-center">
                  <span className="text-[10px] font-mono font-bold text-[var(--brand-hover)] bg-[var(--brand-soft)] px-2 py-0.5 rounded border border-[var(--brand)]/30">
                    ACTIVE MODEL
                  </span>
                  <span className="text-[10px] font-mono text-[var(--text-secondary)] bg-[var(--bg-surface)] px-2 py-0.5 rounded border border-[var(--border-subtle)]">
                    {activeModel}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Feature Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {[
              { title: 'Verification-First', desc: '5-stage DAG: every patch must pass reproduction tests in an isolated sandbox before acceptance.', icon: ShieldCheck, color: 'var(--success)' },
              { title: 'SHA-256 Proof Chains', desc: 'Every artifact is hash-chained into a tamper-evident root seal — verified client-side via Web Crypto.', icon: ShieldCheck, color: 'var(--brand)' },
              { title: 'Isolated Sandboxes', desc: 'gVisor containers with DENY_ALL egress ensure patches execute safely without external access.', icon: ShieldCheck, color: 'var(--cyan)' },
            ].map((feat, idx) => (
              <div key={idx} className="loom-card loom-glow-card">
                <div className="flex items-center gap-2 mb-2">
                  <div className="h-7 w-7 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${feat.color}15`, color: feat.color }}>
                    <feat.icon className="h-3.5 w-3.5" />
                  </div>
                  <h4 className="text-xs font-bold text-[var(--text-primary)] font-mono">{feat.title}</h4>
                </div>
                <p className="text-[11px] text-[var(--text-muted)] leading-relaxed">{feat.desc}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 3. 5-STAGE EXECUTION GRAPH ── */}
      {displayData && (
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
      )}

      {/* ── 4. ACTIVE RUN WORKSTATION ── */}
      {displayData && (
        <div className="loom-card flex flex-col gap-4">
          {/* Run Metadata Banner */}
          <div className="flex items-start justify-between flex-wrap gap-3 pb-4 border-b border-[var(--border-subtle)]">
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-xs font-mono font-bold text-[var(--brand)]">{displayData.id}</span>
              <span className={`status-pill ${displayData.status === 'VERIFIED SUCCESS' ? 'status-pill-verified' : 'status-pill-running'} text-[9px] py-0`}>
                {displayData.status}
              </span>
              <span className="text-[11px] font-mono text-[var(--text-muted)]">
                {displayData.issue}
              </span>
            </div>
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-[10px] font-mono text-[var(--text-muted)] bg-[var(--bg-surface)] px-2 py-0.5 rounded border border-[var(--border-subtle)]">
                {connectedRepo ? 'ACTIVE MODEL' : 'Model'}: <span className="text-[var(--text-secondary)]">{displayData.model || activeModel}</span>
              </span>
              <span className="text-[10px] font-mono text-[var(--text-muted)] bg-[var(--bg-surface)] px-2 py-0.5 rounded border border-[var(--border-subtle)]">
                Repo: <span className="text-[var(--text-secondary)] truncate max-w-[120px] inline-block">{repoName}</span>
              </span>
              <span className="text-[10px] font-mono text-[var(--text-muted)] bg-[var(--bg-surface)] px-2 py-0.5 rounded border border-[var(--border-subtle)]">
                Duration: <span className="text-[var(--cyan)]">{displayData.duration}</span>
              </span>
              <span className="text-[10px] font-mono text-[var(--text-muted)] bg-[var(--bg-surface)] px-2 py-0.5 rounded border border-[var(--border-subtle)]">
                Cost: <span className="text-[var(--success)]">{displayData.cost}</span>
              </span>
              {true && (
                <button
                  onClick={handleRollbackClick}
                  onBlur={() => setRollbackArmed(false)}
                  className={`flex items-center gap-1.5 h-7 px-3 text-[11px] font-mono font-bold rounded-lg border transition-all duration-200 ${
                    rollbackArmed
                      ? 'bg-[var(--danger)]/15 border-[var(--danger)]/50 text-[var(--danger)] shadow-[0_0_12px_rgba(255,95,109,0.2)] animate-pulse'
                      : 'border border-[var(--border-subtle)] text-[var(--text-muted)] hover:border-[var(--danger)]/30 hover:text-[var(--danger)]'
                  }`}
                  title={rollbackArmed ? 'Click again to confirm rollback' : 'Rollback workspace to snapshot'}
                >
                  <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                  <span>{rollbackArmed ? 'Confirm Rollback' : 'Rollback'}</span>
                </button>
              )}
            </div>
          </div>

          {/* Pill Tab Strip */}
          <div className="flex items-center gap-1 border-b border-[var(--border-subtle)] pb-1 overflow-x-auto" role="tablist" aria-label="Run inspection tabs">
            {subtabs.map(tab => {
              const Icon = tab.icon;
              const isActive = detailTab === tab.id;
              return (
                <button
                  key={tab.id}
                  role="tab"
                  aria-selected={isActive}
                  aria-controls={`subpanel-${tab.id}`}
                  id={`subtab-${tab.id}`}
                  onClick={() => setDetailTab(tab.id)}
                  className={`subtab-pill ${isActive ? 'subtab-pill-active' : ''}`}
                >
                  <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          {/* ── Subtab: Overview ── */}
          {detailTab === 'overview' && (
            <div className="space-y-4 animate-fade-in">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="p-3.5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl space-y-1">
                  <div className="flex items-center gap-1.5">
                    <Terminal className="h-3 w-3 text-[var(--cyan)]" aria-hidden="true" />
                    <p className="text-[10px] text-[var(--text-muted)] uppercase font-bold font-mono">Execution Time</p>
                  </div>
                  <p className="text-sm font-bold text-[var(--text-primary)] font-mono">{displayData.duration}</p>
                  <p className="text-[10px] text-[var(--text-muted)]">Recorded run duration</p>
                </div>
                <div className="p-3.5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl space-y-1">
                  <div className="flex items-center gap-1.5">
                    <ShieldCheck className="h-3 w-3 text-[var(--success)]" aria-hidden="true" />
                    <p className="text-[10px] text-[var(--text-muted)] uppercase font-bold font-mono">Inference & Sandbox Cost</p>
                  </div>
                  <p className="text-sm font-bold text-[var(--success)] font-mono">{displayData.cost}</p>
                  <p className="text-[10px] text-[var(--text-muted)]">Tracked step attribution</p>
                </div>
                <div className="p-3.5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl space-y-1">
                  <div className="flex items-center gap-1.5">
                    <CheckCircle2 className={`h-3 w-3 ${displayData.status === 'VERIFIED SUCCESS' ? 'text-[var(--success)]' : 'text-[var(--cyan)]'}`} aria-hidden="true" />
                    <p className="text-[10px] text-[var(--text-muted)] uppercase font-bold font-mono">Verification Status</p>
                  </div>
                  <p className={`text-sm font-bold font-mono ${displayData.status === 'VERIFIED SUCCESS' ? 'text-[var(--success)]' : 'text-[var(--cyan)]'}`}>
                    {displayData.status}
                  </p>
                  <p className="text-[10px] text-[var(--text-muted)]">Tied to {repoName}</p>
                </div>
              </div>

              {/* Resolution Summary */}
              <div className="loom-card-active space-y-3 p-4">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-mono font-bold text-[var(--brand-hover)] bg-[var(--brand-soft)] px-2 py-0.5 rounded border border-[var(--brand)]/30 uppercase">
                      Plain-Language Brief
                    </span>
                    <h4 className="text-xs font-bold text-[var(--text-primary)] font-mono uppercase">
                      Resolution Summary &amp; Verification Proof
                    </h4>
                  </div>
                  <span className="text-[10px] font-mono text-[var(--text-muted)]">Synthesized by Reviewer Agent</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                  {[
                    { label: 'Root Cause Diagnosis', cls: 'text-[var(--danger)]', content: displayData?.checkpoint?.resolution_summary?.root_cause || displayData?.resolution_summary?.root_cause || (displayData?.issue ? `Reproduced issue condition in ${repoName}: ${displayData.issue}` : 'Pending root cause analysis from reproduction stage.') },
                    { label: 'Surgical Modification', cls: 'text-[var(--brand-hover)]', content: displayData?.checkpoint?.resolution_summary?.surgical_change || displayData?.resolution_summary?.surgical_change || (displayData?.patchDiff ? 'Applied minimal AST-guided patch to target source files.' : 'Pending patch synthesis from patcher agent.') },
                    { label: 'Verification Outcome', cls: 'text-[var(--success)]', content: displayData?.checkpoint?.resolution_summary?.verification_proof || displayData?.resolution_summary?.verification_proof || (displayData?.status === 'VERIFIED SUCCESS' ? 'Deterministic reproduction test passed in isolated gVisor sandbox with 0 regressions.' : 'Sandbox test verification in progress or pending.') },
                  ].map(col => (
                    <div key={col.label} className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg space-y-1.5">
                      <p className={`text-[10px] font-bold font-mono ${col.cls} uppercase`}>{col.label}</p>
                      <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{col.content}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Stage Breakdown */}
              <div className="space-y-1.5">
                <h4 className="text-[11px] font-bold text-[var(--text-muted)] uppercase tracking-wider font-mono">
                  Stage Execution Breakdown
                </h4>
                {stages.map((stage) => {
                  const statusAccent =
                    stage.status === 'SUCCEEDED' || stage.status === 'VERIFIED'
                      ? 'stage-card-succeeded'
                      : stage.status === 'RUNNING'
                        ? 'stage-card-running'
                        : stage.status === 'FAILED'
                          ? 'stage-card-failed'
                          : 'stage-card-idle';
                  return (
                    <div
                      key={stage.id}
                      className={`p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl flex items-center justify-between gap-3 text-xs ${statusAccent}`}
                    >
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-[9px] font-bold text-[var(--brand)] bg-[var(--brand-soft)] px-1.5 py-0.5 rounded shrink-0">
                          {stage.number}
                        </span>
                        <div>
                          <p className="font-bold text-[var(--text-primary)] font-mono text-xs">{stage.name}</p>
                          <p className="text-[10px] text-[var(--text-muted)]">{stage.role}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3 font-mono text-[10px] shrink-0">
                        <span className="text-[var(--cyan)] bg-[var(--bg-surface)] px-1.5 py-0.5 rounded border border-[var(--border-subtle)] hidden sm:inline truncate max-w-[120px]" title={stage.model}>
                          {stage.model}
                        </span>
                        <span className="text-[var(--text-secondary)]">{stage.duration}</span>
                        <span className="text-[var(--text-muted)]">{stage.cost}</span>
                        <span className={`font-bold min-w-[50px] text-right ${
                          stage.status === 'SUCCEEDED' || stage.status === 'VERIFIED' ? 'text-[var(--success)]' :
                          stage.status === 'RUNNING' ? 'text-[var(--cyan)]' :
                          'text-[var(--text-muted)]'
                        }`}>
                          {stage.status}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ── Subtab: Diff ── */}
          {detailTab === 'diff' && (
            <div className="space-y-2 animate-fade-in">
              <div className="flex items-center justify-between text-xs font-mono text-[var(--text-muted)]">
                <span className="font-bold uppercase tracking-wider">Verified Surgical Diff</span>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(displayData.patchDiff || '');
                    setCopiedDiff(true);
                    setTimeout(() => setCopiedDiff(false), 2000);
                  }}
                  className="btn-secondary h-6 px-2.5 text-[10px] gap-1"
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

          {/* ── Subtab: Tests ── */}
          {detailTab === 'tests' && (
            <div className="space-y-3 animate-fade-in">
              <div className="p-3.5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-[var(--text-primary)] font-mono uppercase tracking-wider">
                    Reproduction Test Case (Red → Green)
                  </span>
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

          {/* ── Subtab: Sandbox ── */}
          {detailTab === 'sandbox' && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 font-mono animate-fade-in">
              <div className="p-3.5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl space-y-1">
                <div className="flex items-center gap-1.5">
                  <Box className="h-3.5 w-3.5 text-[var(--cyan)]" aria-hidden="true" />
                  <p className="text-[10px] text-[var(--text-muted)] uppercase font-bold">Isolation Tier</p>
                </div>
                <p className="text-sm font-bold text-[var(--cyan)]">Tier B (Container)</p>
                <p className="text-[10px] text-[var(--text-muted)]">gVisor Sandbox Isolation</p>
              </div>
              <div className="p-3.5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl space-y-1">
                <div className="flex items-center gap-1.5">
                  <ShieldCheck className="h-3.5 w-3.5 text-[var(--success)]" aria-hidden="true" />
                  <p className="text-[10px] text-[var(--text-muted)] uppercase font-bold">Egress Restrictions</p>
                </div>
                <p className="text-sm font-bold text-[var(--success)]">DENY_ALL</p>
                <p className="text-[10px] text-[var(--text-muted)]">Strict egress firewall active</p>
              </div>
              <div className="p-3.5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl space-y-1">
                <div className="flex items-center gap-1.5">
                  <GitBranch className="h-3.5 w-3.5 text-[var(--text-secondary)]" aria-hidden="true" />
                  <p className="text-[10px] text-[var(--text-muted)] uppercase font-bold">Target Environment</p>
                </div>
                <p className="text-sm font-bold text-[var(--text-primary)] truncate">{repoName}</p>
                <p className="text-[10px] text-[var(--text-muted)]">{branchName}</p>
              </div>
            </div>
          )}

          {/* ── Subtab: Evidence ── */}
          {detailTab === 'evidence' && (
            <div className="animate-fade-in">
              <EvidenceView displayData={displayData} runId={displayData.id} connectedRepoName={repoName} onOpenLiveBox={onOpenLiveBox} />
            </div>
          )}
        </div>
      )}

      {/* ── 5. GITHUB ISSUES & QUICK ACTIONS ── */}
      {githubIssues.length > 0 ? (
        <div className="loom-card space-y-2.5">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider font-mono">
              Open Issues in {connectedRepo?.name || repoName}
            </h3>
            {onOpenIssuesDrawer && (
              <button
                onClick={onOpenIssuesDrawer}
                className="text-[11px] font-mono text-[var(--brand-hover)] hover:underline transition"
              >
                View all ({githubIssues.length}) →
              </button>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
            {githubIssues.slice(0, 4).map((issue) => (
              <button
                key={issue.number}
                onClick={() => onSelectStarterIssue?.(`#${issue.number}: ${issue.title}\n\n${issue.body || ''}`)}
                className="p-3 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-subtle)] hover:border-[var(--brand)] hover:bg-[var(--bg-hover)] text-left transition-all duration-200 flex items-start gap-2.5 group loom-glow-card"
              >
                <span className="text-xs font-mono font-bold text-[var(--brand)] shrink-0 bg-[var(--brand-soft)] px-1.5 py-0.5 rounded group-hover:bg-[var(--brand)]/20 transition">
                  #{issue.number}
                </span>
                <div className="min-w-0 flex-1">
                  <h4 className="text-xs font-medium text-[var(--text-primary)] group-hover:text-[var(--brand-hover)] transition leading-snug line-clamp-2">
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
                className="p-3 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-subtle)] hover:border-[var(--brand)] hover:bg-[var(--bg-hover)] text-left transition-all duration-200 flex items-start gap-2.5 group loom-glow-card"
              >
                <span className="text-xs font-mono font-bold text-[var(--brand)] shrink-0 bg-[var(--brand-soft)] px-1.5 py-0.5 rounded group-hover:bg-[var(--brand)]/20 transition">
                  {idx === 0 ? '���' : idx === 1 ? '🔧' : '🔒'}
                </span>
                <span className="text-xs font-medium text-[var(--text-primary)] group-hover:text-[var(--brand-hover)] transition leading-snug font-mono">
                  {action.title}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
