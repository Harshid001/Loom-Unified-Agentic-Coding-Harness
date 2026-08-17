"use client";

import React, { useState } from 'react';
import Link from 'next/link';
import {
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
} from 'lucide-react';
import { Github } from './GithubIcon';
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
    title: 'Context Manager Bugfix',
    issue: 'Fix token budget estimation edge case in context manager',
    desc: 'Prevents truncation on multi-file AST call graphs',
  },
  {
    icon: '🛡️',
    title: 'OAuth Security Guard',
    issue: 'Implement cryptographic state verification for OAuth redirects',
    desc: 'Protects against cross-origin replay attacks',
  },
  {
    icon: '📈',
    title: 'AST Graph Optimizer',
    issue: 'Optimize AST call graph dependency indexer for Python & TypeScript',
    desc: 'Enhances Tree-Sitter symbol resolution speed',
  },
  {
    icon: '🧪',
    title: 'Sandbox Test Suite',
    issue: 'Synthesize regression test suite for sandbox tier guards',
    desc: 'Verifies container egress isolation policies',
  },
];

export const OverviewTab: React.FC<OverviewTabProps> = ({
  displayData,
  selectedRun,
  onRollback,
  isLoadingDetails,
  onOpenLiveBox,
  onSelectStarterIssue,
  activeModel = 'gemini-1.5-pro',
  connectedRepo,
  githubIssues = [],
  onOpenRepoModal,
  onOpenIssuesDrawer,
}) => {
  const [expandedLog, setExpandedLog] = useState<string | null>(null);
  const [taskViewMode, setTaskViewMode] = useState<'starters' | 'github'>(
    githubIssues.length > 0 ? 'github' : 'starters'
  );

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
      <div className="flex-1 flex flex-col gap-6" id="tabpanel-overview" role="tabpanel" aria-labelledby="tab-overview">
        {/* Hero Onboarding Card */}
        <div className="relative overflow-hidden bg-gradient-to-br from-indigo-950/40 via-[#111827] to-gray-900 border border-indigo-500/20 rounded-2xl p-6 lg:p-8 shadow-xl">
          <div className="absolute top-0 right-0 -mr-16 -mt-16 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
          
          <div className="flex items-center gap-2 text-indigo-400 text-xs font-semibold uppercase tracking-wider mb-2">
            <Sparkles className="h-4 w-4 text-indigo-400" />
            <span>Autonomous Coding Harness</span>
          </div>

          <h2 className="text-xl lg:text-2xl font-bold text-white mb-2">
            Welcome to Loom — Next-Gen Multi-Agent Engineering
          </h2>
          <p className="text-xs lg:text-sm text-gray-300 max-w-3xl leading-relaxed mb-6">
            Loom executes automated software engineering workflows using a 5-stage DAG pipeline with strict state machine preconditions, sandbox isolation, and cryptographic evidence verification.
          </p>

          {/* 3-Step Guided Action Flow */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Step 1 */}
            <div className="bg-gray-900/80 border border-gray-800 rounded-xl p-4 flex flex-col justify-between hover:border-gray-700 transition">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono font-bold text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">STEP 1</span>
                  <Cpu className="h-4 w-4 text-gray-400" />
                </div>
                <h3 className="text-xs font-bold text-white mb-1">Active Model</h3>
                <p className="text-[11px] text-gray-400 font-mono mb-2 truncate">{activeModel}</p>
                <div className="flex items-center gap-1.5 text-[10px] text-emerald-400 mb-3">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  <span>Ready for execution</span>
                </div>
              </div>
              <Link
                href="/settings/models"
                className="text-[11px] text-indigo-400 hover:text-indigo-300 font-medium flex items-center gap-1 mt-auto"
              >
                <span>Manage API Keys & Models</span>
                <ArrowRight className="h-3 w-3" />
              </Link>
            </div>

            {/* Step 2 */}
            <div className="bg-gray-900/80 border border-gray-800 rounded-xl p-4 flex flex-col justify-between hover:border-gray-700 transition">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono font-bold text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">STEP 2</span>
                  <Zap className="h-4 w-4 text-amber-400" />
                </div>
                <h3 className="text-xs font-bold text-white mb-1">Enter Any Issue</h3>
                <p className="text-[11px] text-gray-400 mb-3">
                  Describe any bug fix, feature, or refactoring task in the top input box.
                </p>
              </div>
              <button
                onClick={onOpenLiveBox}
                className="text-[11px] text-amber-400 hover:text-amber-300 font-medium flex items-center gap-1 mt-auto"
              >
                <span>Type Custom Task ➔</span>
              </button>
            </div>

            {/* Step 3 */}
            <div className="bg-gray-900/80 border border-indigo-500/30 rounded-xl p-4 flex flex-col justify-between shadow-lg shadow-indigo-950/20">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono font-bold text-indigo-300 bg-indigo-500/20 px-2 py-0.5 rounded border border-indigo-500/30">STEP 3</span>
                  <GitBranch className="h-4 w-4 text-indigo-400" />
                </div>
                <h3 className="text-xs font-bold text-white mb-1">Execute & Inspect</h3>
                <p className="text-[11px] text-gray-400 mb-3">
                  Stream real-time agent steps, unified patch diffs, and evidence bundles.
                </p>
              </div>
              <button
                onClick={onOpenLiveBox}
                className="w-full py-2 bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white rounded-lg text-xs font-semibold transition flex items-center justify-center gap-1.5 shadow-md"
              >
                <Zap className="h-3.5 w-3.5 fill-current" />
                <span>Launch Live Box</span>
              </button>
            </div>
          </div>
        </div>

        {/* Connected Repository & GitHub Workspace Banner */}
        <div className="bg-gradient-to-r from-gray-900 via-[#111827] to-gray-900 border border-gray-800 rounded-2xl p-5 shadow-lg">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-3.5">
              <div className="h-11 w-11 rounded-xl bg-gradient-to-br from-indigo-600/30 to-purple-600/30 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shadow-inner">
                <FolderGit2 className="h-6 w-6" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">
                    Target Repository
                  </span>
                  {connectedRepo?.isPrivate ? (
                    <span className="text-[10px] bg-amber-500/10 text-amber-400 px-1.5 py-0.2 rounded border border-amber-500/30">
                      Private
                    </span>
                  ) : (
                    <span className="text-[10px] bg-emerald-500/10 text-emerald-400 px-1.5 py-0.2 rounded border border-emerald-500/30">
                      Public
                    </span>
                  )}
                </div>
                <h3 className="text-sm font-bold text-white font-mono flex items-center gap-2 mt-0.5">
                  {connectedRepo?.fullName || 'No Repository Connected'}
                  {connectedRepo?.htmlUrl && (
                    <a
                      href={connectedRepo.htmlUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="text-gray-400 hover:text-indigo-400 transition"
                      title="View on GitHub"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  )}
                </h3>
                {connectedRepo?.description && (
                  <p className="text-xs text-gray-400 max-w-xl truncate mt-0.5">
                    {connectedRepo.description}
                  </p>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2.5">
              {connectedRepo?.selectedBranch && (
                <div className="text-xs font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-3 py-1.5 rounded-lg flex items-center gap-1.5">
                  <GitBranch className="h-3.5 w-3.5" />
                  <span>{connectedRepo.selectedBranch}</span>
                </div>
              )}

              {onOpenIssuesDrawer && (
                <button
                  onClick={onOpenIssuesDrawer}
                  className="flex items-center gap-1.5 text-xs bg-indigo-950/60 hover:bg-indigo-900/60 text-indigo-300 border border-indigo-500/30 hover:border-indigo-500/60 px-3.5 py-2 rounded-xl font-semibold transition"
                >
                  <ListTodo className="h-4 w-4 text-indigo-400" />
                  <span>Browse GitHub Issues ({githubIssues.length})</span>
                </button>
              )}

              {onOpenRepoModal && (
                <button
                  onClick={onOpenRepoModal}
                  className="flex items-center gap-1.5 text-xs bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 px-3.5 py-2 rounded-xl font-semibold transition"
                >
                  <Github className="h-4 w-4 text-gray-300" />
                  <span>Connect / Switch Repo</span>
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Tasks Section: Toggle between Starter Workflows and Live GitHub Issues */}
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-6">
          <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
            <div>
              <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
                1-Click Issues & Tasks
              </h3>
              <p className="text-xs text-gray-500">
                Select any task or GitHub issue below to immediately launch an autonomous pipeline execution
              </p>
            </div>

            <div className="flex items-center bg-gray-900 border border-gray-800 rounded-xl p-1 text-xs">
              <button
                onClick={() => setTaskViewMode('starters')}
                className={`px-3 py-1 rounded-lg transition ${
                  taskViewMode === 'starters'
                    ? 'bg-indigo-600 text-white font-semibold'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                Starter Tasks
              </button>
              <button
                onClick={() => setTaskViewMode('github')}
                className={`px-3 py-1 rounded-lg transition flex items-center gap-1.5 ${
                  taskViewMode === 'github'
                    ? 'bg-indigo-600 text-white font-semibold'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                <Github className="h-3 w-3" />
                <span>GitHub Issues ({githubIssues.length})</span>
              </button>
            </div>
          </div>

          {taskViewMode === 'starters' ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {STARTER_TASKS.map((task, idx) => (
                <button
                  key={idx}
                  onClick={() => onSelectStarterIssue?.(task.issue)}
                  className="flex items-start gap-3.5 p-4 rounded-xl bg-gray-900/60 border border-gray-800/80 hover:border-indigo-500/40 hover:bg-gray-900 text-left transition group"
                >
                  <span className="text-2xl p-2 rounded-lg bg-gray-800/80 group-hover:scale-110 transition shrink-0">
                    {task.icon}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-bold text-white group-hover:text-indigo-300 transition">
                        {task.title}
                      </h4>
                      <span className="text-[10px] text-indigo-400 font-medium opacity-0 group-hover:opacity-100 transition flex items-center gap-0.5">
                        <span>Run</span>
                        <ArrowRight className="h-3 w-3" />
                      </span>
                    </div>
                    <p className="text-xs text-gray-300 font-mono mt-0.5 truncate">{task.issue}</p>
                    <p className="text-[11px] text-gray-500 mt-1">{task.desc}</p>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {githubIssues.length === 0 ? (
                <div className="col-span-2 text-center py-8 text-xs text-gray-500 bg-gray-900/30 rounded-xl border border-gray-800">
                  No open issues found for {connectedRepo?.fullName || 'the connected repository'}.
                </div>
              ) : (
                githubIssues.slice(0, 4).map(issue => (
                  <button
                    key={issue.id}
                    onClick={() =>
                      onSelectStarterIssue?.(
                        `[GitHub Issue #${issue.number}] ${issue.title}\n\n${issue.body || ''}`.trim()
                      )
                    }
                    className="flex items-start gap-3.5 p-4 rounded-xl bg-gray-900/60 border border-gray-800/80 hover:border-indigo-500/40 hover:bg-gray-900 text-left transition group"
                  >
                    <div className="h-9 w-9 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-emerald-400 font-mono text-xs font-bold shrink-0">
                      #{issue.number}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <h4 className="text-xs font-bold text-white group-hover:text-indigo-300 transition truncate">
                          {issue.title}
                        </h4>
                        {issue.comments > 0 && (
                          <span className="text-[10px] text-gray-400 flex items-center gap-0.5 font-mono shrink-0">
                            <MessageSquare className="h-3 w-3" />
                            {issue.comments}
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-gray-400 line-clamp-2 mt-1">
                        {issue.body || 'No description provided.'}
                      </p>
                      {issue.labels && issue.labels.length > 0 && (
                        <div className="flex items-center gap-1.5 flex-wrap mt-2">
                          {issue.labels.slice(0, 3).map(l => (
                            <span
                              key={l.id}
                              className="text-[9px] px-1.5 py-0.5 rounded font-mono"
                              style={{ backgroundColor: `#${l.color}20`, color: `#${l.color}` }}
                            >
                              {l.name}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {/* Multi-Agent DAG Architecture Breakdown */}
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-6">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">
            5-Stage Autonomous DAG Architecture
          </h3>
          <p className="text-xs text-gray-500 mb-4">
            How Loom prevents regressions and guarantees verified code modifications
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-5 gap-2.5">
            <div className="p-3 bg-gray-900/60 border border-gray-800 rounded-lg text-center">
              <span className="text-[10px] font-bold text-indigo-400 font-mono">1. ONBOARDING</span>
              <p className="text-xs font-semibold text-white mt-1">Repo Mapper</p>
              <p className="text-[10px] text-gray-500 mt-1">AST Tree & Proximity Call Graph</p>
            </div>
            <div className="p-3 bg-gray-900/60 border border-gray-800 rounded-lg text-center">
              <span className="text-[10px] font-bold text-amber-400 font-mono">2. REPRODUCTION</span>
              <p className="text-xs font-semibold text-white mt-1">Reproduction Agent</p>
              <p className="text-[10px] text-gray-500 mt-1">Synthesizes failing test (Red phase)</p>
            </div>
            <div className="p-3 bg-gray-900/60 border border-gray-800 rounded-lg text-center">
              <span className="text-[10px] font-bold text-blue-400 font-mono">3. PATCHER</span>
              <p className="text-xs font-semibold text-white mt-1">Patcher Agent</p>
              <p className="text-[10px] text-gray-500 mt-1">Generates surgical code diff</p>
            </div>
            <div className="p-3 bg-gray-900/60 border border-gray-800 rounded-lg text-center">
              <span className="text-[10px] font-bold text-emerald-400 font-mono">4. VERIFIER</span>
              <p className="text-xs font-semibold text-white mt-1">Sandbox Verifier</p>
              <p className="text-[10px] text-gray-500 mt-1">Executes pytest (Green phase)</p>
            </div>
            <div className="p-3 bg-gray-900/60 border border-gray-800 rounded-lg text-center">
              <span className="text-[10px] font-bold text-purple-400 font-mono">5. REVIEWER</span>
              <p className="text-xs font-semibold text-white mt-1">Evidence Reviewer</p>
              <p className="text-[10px] text-gray-500 mt-1">SHA-256 Hash Chain Audit Bundle</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const isSuccess = displayData.status === 'VERIFIED SUCCESS';

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