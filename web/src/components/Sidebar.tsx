"use client";

import React, { useState, useMemo } from 'react';
import Link from 'next/link';
import {
  Activity,
  GitBranch,
  FileCode,
  Layers,
  Search,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  Cpu,
  Box,
  CheckCircle2,
  XCircle,
  Loader2,
  FolderGit2,
  Settings as SettingsIcon,
  Key,
  TestTube2,
  Play,
  Circle,
} from 'lucide-react';
import { RunItem } from '../hooks/useRuns';

export type LifecycleTab =
  | 'overview'
  | 'runs'
  | 'dag'
  | 'agents'
  | 'sandbox'
  | 'diff'
  | 'tests'
  | 'evidence'
  | 'ablations';

interface SidebarProps {
  activeTab: LifecycleTab;
  setActiveTab: (tab: LifecycleTab) => void;
  runHistory: RunItem[];
  selectedRun: string | null;
  setSelectedRun: (id: string) => void;
  isLoadingRuns: boolean;
  onOpenRepoModal?: () => void;
  onOpenApiKeyModal?: () => void;
  connectedRepoName?: string;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  runHistory,
  selectedRun,
  setSelectedRun,
  isLoadingRuns,
  onOpenRepoModal,
  onOpenApiKeyModal,
  connectedRepoName = 'No Repository Connected',
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'pass' | 'fail' | 'exec'>('all');
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 4;

  const workspaceNav = [
    { id: 'overview' as const, icon: Activity, label: 'Overview' },
    { id: 'runs' as const, icon: Play, label: 'Runs' },
    { id: 'dag' as const, icon: GitBranch, label: 'DAG Execution' },
  ];

  const engineeringNav = [
    { id: 'agents' as const, icon: Cpu, label: 'Agents' },
    { id: 'sandbox' as const, icon: Box, label: 'Sandbox' },
    { id: 'diff' as const, icon: FileCode, label: 'Patches' },
  ];

  const verificationNav = [
    { id: 'tests' as const, icon: TestTube2, label: 'Tests' },
    { id: 'evidence' as const, icon: ShieldCheck, label: 'Evidence' },
    { id: 'ablations' as const, icon: Layers, label: 'Ablations' },
  ];

  const passedCount = runHistory.filter(r => r.status === 'VERIFIED SUCCESS').length;

  const filteredRuns = useMemo(() => {
    return runHistory.filter(r => {
      const matchesSearch =
        !searchQuery.trim() ||
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

  const renderNavGroup = (title: string, items: { id: LifecycleTab; icon: any; label: string }[]) => (
    <div className="mb-4">
      <h3 className="text-[10px] font-mono font-bold text-[var(--text-muted)] uppercase tracking-wider px-2 mb-1.5">
        {title}
      </h3>
      <nav className="space-y-0.5" aria-label={title}>
        {items.map(item => {
          const isActive = activeTab === item.id;
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              aria-pressed={isActive}
              aria-controls={`tabpanel-${item.id}`}
              id={`tab-${item.id}`}
              className={`w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition ${
                isActive
                  ? 'bg-[var(--brand-soft)] text-[var(--brand-hover)] border border-[var(--brand)]/30 font-semibold'
                  : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] border border-transparent'
              }`}
            >
              <Icon className={`h-3.5 w-3.5 ${isActive ? 'text-[var(--brand)]' : 'text-[var(--text-muted)]'}`} aria-hidden="true" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );

  return (
    <aside className="w-60 flex flex-col gap-3 shrink-0" aria-label="Harness Navigation">
      {/* 1. Harness Lifecycle Navigation Card */}
      <div className="bg-[var(--bg-sidebar)] border border-[var(--border-subtle)] rounded-xl p-3">
        {renderNavGroup('WORKSPACE', workspaceNav)}
        {renderNavGroup('ENGINEERING', engineeringNav)}
        {renderNavGroup('VERIFICATION', verificationNav)}

        {/* System Controls at Bottom of Nav */}
        <div className="pt-3 border-t border-[var(--border-subtle)] space-y-0.5">
          <h3 className="text-[10px] font-mono font-bold text-[var(--text-muted)] uppercase tracking-wider px-2 mb-1.5">
            SYSTEM
          </h3>
          {onOpenRepoModal && (
            <button
              onClick={onOpenRepoModal}
              aria-label="Target repository configuration"
              className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition"
            >
              <div className="flex items-center gap-2 truncate">
                <FolderGit2 className="h-3.5 w-3.5 text-[var(--text-muted)] shrink-0" aria-hidden="true" />
                <span className="truncate">{connectedRepoName}</span>
              </div>
            </button>
          )}

          <Link
            href="/settings/models"
            aria-label="Open model settings"
            className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition"
          >
            <SettingsIcon className="h-3.5 w-3.5 text-[var(--text-muted)]" aria-hidden="true" />
            <span>Model Settings</span>
          </Link>

          {onOpenApiKeyModal && (
            <button
              onClick={onOpenApiKeyModal}
              aria-label="Manage API keys"
              className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition"
            >
              <Key className="h-3.5 w-3.5 text-[var(--text-muted)]" aria-hidden="true" />
              <span>API Keys</span>
            </button>
          )}
        </div>
      </div>

      {/* 2. Execution Runs Drawer / List */}
      <div className="bg-[var(--bg-sidebar)] border border-[var(--border-subtle)] rounded-xl p-3 flex-1 flex flex-col min-h-0">
        <div className="flex items-center justify-between mb-2 px-1">
          <div className="flex items-center gap-1.5">
            <h3 className="text-[10px] font-mono font-bold text-[var(--text-muted)] uppercase tracking-wider">
              RUNS HISTORY
            </h3>
            <span className="text-[10px] font-mono text-[var(--text-muted)] bg-[var(--bg-elevated)] px-1.5 py-0.2 rounded border border-[var(--border-subtle)]">
              {runHistory.length}
            </span>
          </div>
        </div>

        {/* Filter & Search */}
        <div className="space-y-1.5 mb-2">
          <div className="relative">
            <Search className="h-3 w-3 absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" aria-hidden="true" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => {
                setSearchQuery(e.target.value);
                setCurrentPage(1);
              }}
              aria-label="Filter runs history"
              placeholder="Filter runs..."
              className="w-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-lg pl-7 pr-2 py-1 text-[11px] text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--brand)] font-mono"
            />
          </div>
          <div className="flex items-center gap-1" role="group" aria-label="Status filters">
            {(['all', 'pass', 'fail', 'exec'] as const).map(filter => (
              <button
                key={filter}
                onClick={() => {
                  setStatusFilter(filter);
                  setCurrentPage(1);
                }}
                aria-pressed={statusFilter === filter}
                aria-label={`Filter by ${filter} status`}
                className={`flex-1 py-0.5 text-[9px] uppercase font-mono font-bold rounded transition ${
                  statusFilter === filter
                    ? 'bg-[var(--brand-soft)] text-[var(--brand-hover)] border border-[var(--brand)]/30'
                    : 'bg-[var(--bg-surface)] text-[var(--text-muted)] hover:text-[var(--text-primary)] border border-[var(--border-subtle)]'
                }`}
              >
                {filter}
              </button>
            ))}
          </div>
        </div>

        {/* Runs List Items */}
        {isLoadingRuns ? (
          <div className="flex-1 flex items-center justify-center py-6" aria-live="polite">
            <Loader2 className="h-4 w-4 text-[var(--text-muted)] animate-spin" aria-hidden="true" />
          </div>
        ) : filteredRuns.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-3 gap-1">
            <Circle className="h-4 w-4 text-[var(--text-muted)]" aria-hidden="true" />
            <p className="text-[11px] text-[var(--text-muted)]">No recorded runs</p>
          </div>
        ) : (
          <div className="flex-1 flex flex-col min-h-0">
            <div className="space-y-1 overflow-y-auto flex-1 pr-0.5" role="feed" aria-label="Historical runs">
              {paginatedRuns.map(run => {
                const isSelected = selectedRun === run.id;
                const isPassed = run.status === 'VERIFIED SUCCESS';
                const isFailed = run.status === 'FAILED';

                return (
                  <button
                    key={run.id}
                    onClick={() => {
                      setSelectedRun(run.id);
                      setActiveTab('overview');
                    }}
                    aria-label={`Select run ${run.id}: ${run.issue}`}
                    className={`w-full text-left p-2 rounded-lg border transition ${
                      isSelected
                        ? 'bg-[var(--brand-soft)] border-[var(--brand)] text-[var(--text-primary)] shadow-sm'
                        : 'bg-[var(--bg-surface)] border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--border-default)]'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="font-mono text-[10px] font-bold text-[var(--brand-hover)]">
                        {run.id}
                      </span>
                      <span
                        className={`text-[9px] px-1.5 py-0.2 rounded font-mono font-bold uppercase ${
                          isPassed
                            ? 'text-[var(--success)] bg-[var(--success)]/10'
                            : isFailed
                            ? 'text-[var(--danger)] bg-[var(--danger)]/10'
                            : 'text-[var(--cyan)] bg-[var(--cyan)]/10'
                        }`}
                      >
                        {isPassed ? 'PASS' : isFailed ? 'FAIL' : 'EXEC'}
                      </span>
                    </div>
                    <p className="text-[11px] line-clamp-1 text-[var(--text-primary)] font-sans">
                      {run.issue}
                    </p>
                  </button>
                );
              })}
            </div>

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between pt-2 border-t border-[var(--border-subtle)] text-[10px] font-mono text-[var(--text-muted)]" aria-label="Runs pagination">
                <span>
                  {currentPage} / {totalPages}
                </span>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    aria-label="Previous page of runs"
                    className="p-1 rounded bg-[var(--bg-surface)] hover:bg-[var(--bg-hover)] disabled:opacity-30 border border-[var(--border-subtle)]"
                  >
                    <ChevronLeft className="h-3 w-3" aria-hidden="true" />
                  </button>
                  <button
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    aria-label="Next page of runs"
                    className="p-1 rounded bg-[var(--bg-surface)] hover:bg-[var(--bg-hover)] disabled:opacity-30 border border-[var(--border-subtle)]"
                  >
                    <ChevronRight className="h-3 w-3" aria-hidden="true" />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
};