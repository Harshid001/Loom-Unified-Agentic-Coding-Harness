"use client";

import React, { useState, useMemo, useCallback, useEffect } from 'react';
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
  Trash2,
  BarChart3,
} from 'lucide-react';
import { RunItem } from '../hooks/useRuns';

export type LifecycleTab =
  | 'overview'
  | 'analytics'
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

interface NavItemDef {
  id: LifecycleTab;
  icon: React.ElementType;
  label: string;
}

interface NavGroupDef {
  title: string;
  items: NavItemDef[];
}

const NAV_GROUPS: NavGroupDef[] = [
  {
    title: 'WORKSPACE',
    items: [
      { id: 'overview', icon: Activity, label: 'Overview' },
      { id: 'analytics', icon: BarChart3, label: 'Analytics' },
      { id: 'dag', icon: GitBranch, label: 'DAG Execution' },
    ],
  },
  {
    title: 'ENGINEERING',
    items: [
      { id: 'agents', icon: Cpu, label: 'Agents' },
      { id: 'sandbox', icon: Box, label: 'Sandbox' },
      { id: 'diff', icon: FileCode, label: 'Patches' },
    ],
  },
  {
    title: 'VERIFICATION',
    items: [
      { id: 'tests', icon: TestTube2, label: 'Tests' },
      { id: 'evidence', icon: ShieldCheck, label: 'Evidence' },
      { id: 'ablations', icon: Layers, label: 'Ablations' },
    ],
  },
];

const ALL_NAV_ITEMS: NavItemDef[] = NAV_GROUPS.flatMap(g => g.items);

const STORAGE_KEY = 'loom_sidebar_collapsed';

function SidebarNavItem({
  item,
  isActive,
  onClick,
  compact,
}: {
  item: NavItemDef;
  isActive: boolean;
  onClick: () => void;
  compact?: boolean;
}) {
  const Icon = item.icon;
  if (compact) {
    return (
      <button
        key={item.id}
        onClick={onClick}
        aria-pressed={isActive}
        aria-label={item.label}
        title={item.label}
        className={`w-9 h-9 flex items-center justify-center rounded-lg transition-all duration-200 shrink-0 ${
          isActive
            ? 'text-[var(--brand)] bg-[var(--brand-soft)] shadow-[0_0_8px_rgba(124,92,255,0.2)]'
            : 'text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]'
        }`}
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
      </button>
    );
  }
  return (
    <button
      key={item.id}
      onClick={onClick}
      aria-pressed={isActive}
      aria-controls={`tabpanel-${item.id}`}
      id={`tab-${item.id}`}
      className={`w-full flex items-center gap-2.5 py-2 rounded-lg text-xs font-medium transition-all duration-200 ${
        isActive
          ? 'sidebar-item-active font-semibold'
          : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] border border-transparent'
      }`}
    >
      <Icon
        className={`h-4 w-4 shrink-0 transition-colors duration-200 ${
          isActive ? 'text-[var(--brand)]' : 'text-[var(--text-muted)]'
        }`}
        aria-hidden="true"
      />
      <span className="sidebar-label truncate">{item.label}</span>
    </button>
  );
}

function NavGroupSection({
  group,
  activeTab,
  onSelect,
  collapsed,
}: {
  group: NavGroupDef;
  activeTab: LifecycleTab;
  onSelect: (id: LifecycleTab) => void;
  collapsed: boolean;
}) {
  if (collapsed) {
    return (
      <nav aria-label={group.title} className="flex flex-col items-center gap-0.5">
        {group.items.map(item => (
          <SidebarNavItem
            key={item.id}
            item={item}
            isActive={activeTab === item.id}
            onClick={() => onSelect(item.id)}
            compact
          />
        ))}
      </nav>
    );
  }
  return (
    <div>
      <h3 className="sidebar-section-title text-[9px] font-mono font-bold text-[var(--text-muted)] uppercase tracking-widest px-2 mb-1.5">
        {group.title}
      </h3>
      <nav className="space-y-0.5" aria-label={group.title}>
        {group.items.map(item => (
          <SidebarNavItem
            key={item.id}
            item={item}
            isActive={activeTab === item.id}
            onClick={() => onSelect(item.id)}
          />
        ))}
      </nav>
    </div>
  );
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
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window !== 'undefined') {
      try { return localStorage.getItem(STORAGE_KEY) === 'true'; } catch { /* ignore */ }
    }
    return false;
  });
  const pageSize = 4;

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, String(collapsed)); } catch { /* ignore */ }
  }, [collapsed]);

  const passedCount = runHistory.filter(r => r.status === 'VERIFIED SUCCESS').length;
  const failedCount = runHistory.filter(r => r.status === 'FAILED').length;
  const execCount   = runHistory.length - passedCount - failedCount;

  const filteredRuns = useMemo(() => {
    return runHistory.filter(r => {
      const matchesSearch =
        !searchQuery.trim() ||
        r.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        r.issue.toLowerCase().includes(searchQuery.toLowerCase());
      const isPass = r.status === 'VERIFIED SUCCESS';
      const isFail = r.status === 'FAILED';
      if (!matchesSearch) return false;
      if (statusFilter === 'pass') return isPass;
      if (statusFilter === 'fail') return isFail;
      if (statusFilter === 'exec') return !isPass && !isFail;
      return true;
    });
  }, [runHistory, searchQuery, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredRuns.length / pageSize));
  const paginatedRuns = filteredRuns.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  const clearSearch = useCallback(() => {
    setSearchQuery('');
    setCurrentPage(1);
  }, []);

  const sidebarWidth = collapsed ? 'w-[56px]' : 'w-60';

  return (
    <aside
      className={`${sidebarWidth} shrink-0 flex flex-col gap-3 transition-all duration-300 ease-out`}
      aria-label="Harness Navigation"
    >
      {/* ── Harness Lifecycle Navigation ── */}
      <div className="bg-[var(--bg-sidebar)] border border-[var(--border-subtle)] rounded-xl overflow-hidden relative">
        {/* Subtle animated top-edge accent */}
        <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-[var(--brand)]/20 to-transparent pointer-events-none" aria-hidden="true" />
        {/* Collapse toggle */}
        <div className="flex items-center justify-between px-2 pt-2">
          {!collapsed && (
            <h3 className="text-[9px] font-mono font-bold text-[var(--text-muted)] uppercase tracking-widest px-1">
              NAVIGATION
            </h3>
          )}
          <button
            onClick={() => setCollapsed(c => !c)}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            title={collapsed ? 'Expand sidebar' : 'Collapse to icons'}
            className="p-1 rounded-md text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition ml-auto"
          >
            {collapsed
              ? <ChevronRight className="h-3 w-3" />
              : <ChevronLeft className="h-3 w-3" />
            }
          </button>
        </div>

        <div className={`${collapsed ? 'p-1.5' : 'p-3'} space-y-5`}>
          {collapsed ? (
            <nav className="flex flex-col items-center gap-0.5" aria-label="Navigation icons">
              {ALL_NAV_ITEMS.map(item => (
                <SidebarNavItem
                  key={item.id}
                  item={item}
                  isActive={activeTab === item.id}
                  onClick={() => setActiveTab(item.id)}
                  compact
                />
              ))}
            </nav>
          ) : (
            <>
              <div className="h-px bg-gradient-to-r from-transparent via-[var(--border-default)] to-transparent" aria-hidden="true" />
              {NAV_GROUPS.map(group => (
                <NavGroupSection
                  key={group.title}
                  group={group}
                  activeTab={activeTab}
                  onSelect={setActiveTab}
                  collapsed={false}
                />
              ))}
            </>
          )}
        </div>

        {/* System Controls (expanded only) */}
        {!collapsed && (
          <div className="px-3 pb-3 pt-1 border-t border-[var(--border-subtle)] space-y-0.5">
            <h3 className="text-[9px] font-mono font-bold text-[var(--text-muted)] uppercase tracking-widest px-2 mb-1.5">
              SYSTEM
            </h3>
            {onOpenRepoModal && (
              <button
                onClick={onOpenRepoModal}
                aria-label="Target repository configuration"
                className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition"
              >
                <FolderGit2 className="h-3.5 w-3.5 text-[var(--text-muted)] shrink-0" aria-hidden="true" />
                <span className="truncate sidebar-label">{connectedRepoName}</span>
              </button>
            )}
            <Link
              href="/settings/models"
              aria-label="Open model settings"
              className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition"
            >
              <SettingsIcon className="h-3.5 w-3.5 text-[var(--text-muted)] shrink-0" aria-hidden="true" />
              <span className="sidebar-label">Model Settings</span>
            </Link>
            {onOpenApiKeyModal && (
              <button
                onClick={onOpenApiKeyModal}
                aria-label="Manage API keys"
                className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition"
              >
                <Key className="h-3.5 w-3.5 text-[var(--text-muted)] shrink-0" aria-hidden="true" />
                <span className="sidebar-label">API Keys</span>
              </button>
            )}
          </div>
        )}
      </div>

      {/* ── Execution Runs Drawer ── */}
      <div className="bg-[var(--bg-sidebar)] border border-[var(--border-subtle)] rounded-xl flex-1 flex flex-col min-h-0 overflow-hidden">
        {!collapsed ? (
          <ExpandedRunsContent
            runHistory={runHistory}
            selectedRun={selectedRun}
            setSelectedRun={setSelectedRun}
            isLoadingRuns={isLoadingRuns}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            statusFilter={statusFilter}
            setStatusFilter={setStatusFilter}
            currentPage={currentPage}
            setCurrentPage={setCurrentPage}
            paginatedRuns={paginatedRuns}
            totalPages={totalPages}
            passedCount={passedCount}
            failedCount={failedCount}
            execCount={execCount}
            onOpenLiveBox={onOpenRepoModal}
            onSetActiveTab={setActiveTab}
          />
        ) : (
          <CollapsedRunsRail activeTab={activeTab} setActiveTab={setActiveTab} />
        )}
      </div>
    </aside>
  );
};

function ExpandedRunsContent({
  runHistory,
  selectedRun,
  setSelectedRun,
  isLoadingRuns,
  searchQuery,
  setSearchQuery,
  statusFilter,
  setStatusFilter,
  currentPage,
  setCurrentPage,
  paginatedRuns,
  totalPages,
  passedCount,
  failedCount,
  execCount,
  onOpenLiveBox,
  onSetActiveTab,
}: {
  runHistory: RunItem[];
  selectedRun: string | null;
  setSelectedRun: (id: string) => void;
  isLoadingRuns: boolean;
  searchQuery: string;
  setSearchQuery: (v: string) => void;
  statusFilter: 'all' | 'pass' | 'fail' | 'exec';
  setStatusFilter: (v: 'all' | 'pass' | 'fail' | 'exec') => void;
  currentPage: number;
  setCurrentPage: (v: number) => void;
  paginatedRuns: RunItem[];
  totalPages: number;
  passedCount: number;
  failedCount: number;
  execCount: number;
  onOpenLiveBox?: () => void;
  onSetActiveTab?: (id: LifecycleTab) => void;
}) {
  const goPrev = useCallback(() => setCurrentPage(Math.max(1, currentPage - 1)), [currentPage, setCurrentPage]);
  const goNext = useCallback(() => setCurrentPage(Math.min(totalPages, currentPage + 1)), [currentPage, totalPages, setCurrentPage]);

  return (
    <>
      {/* Header */}
      <div className="px-3 pt-3 pb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-[10px] font-mono font-bold text-[var(--text-muted)] uppercase tracking-wider">
            Runs History
          </h3>
          <span className="text-[10px] font-mono text-[var(--text-muted)] bg-[var(--bg-elevated)] px-1.5 py-0.5 rounded border border-[var(--border-subtle)]">
            {runHistory.length}
          </span>
        </div>
      </div>

      {/* Stats Summary */}
      {runHistory.length > 0 && (
        <div className="mx-3 mb-2 flex items-center gap-2">
          <div className="flex items-center gap-1.5 text-[10px] font-mono">
            {passedCount > 0 && (
              <span className="text-[var(--success)] flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                {passedCount}
              </span>
            )}
            {failedCount > 0 && (
              <span className="text-[var(--danger)] flex items-center gap-1 ml-1.5">
                <XCircle className="h-3 w-3" aria-hidden="true" />
                {failedCount}
              </span>
            )}
            {execCount > 0 && (
              <span className="text-[var(--cyan)] flex items-center gap-1 ml-1.5">
                <Circle className="h-3 w-3 fill-current" aria-hidden="true" />
                {execCount}
              </span>
            )}
          </div>
          <div className="flex-1 h-1 rounded-full bg-[var(--bg-elevated)] overflow-hidden max-w-[60px]">
            <div
              className="h-full rounded-full bg-gradient-to-r from-[var(--success)] to-[var(--cyan)] transition-all duration-500"
              style={{ width: runHistory.length > 0 ? `${(passedCount / runHistory.length) * 100}%` : '0%' }}
            />
          </div>
        </div>
      )}

      {/* Filter & Search */}
      <div className="px-3 space-y-1.5 mb-2">
        <div className="relative">
          <Search className="h-3 w-3 absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)] pointer-events-none" aria-hidden="true" />
          <input
            type="text"
            value={searchQuery}
            onChange={e => { setSearchQuery(e.target.value); setCurrentPage(1); }}
            aria-label="Filter runs history"
            placeholder="Filter runs..."
            className="w-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-lg pl-7 pr-7 py-1.5 text-[11px] text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--brand)] font-mono transition"
          />
          {searchQuery && (
            <button
              onClick={() => { setSearchQuery(''); setCurrentPage(1); }}
              aria-label="Clear search"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition p-0.5"
            >
              <Trash2 className="h-3 w-3" aria-hidden="true" />
            </button>
          )}
        </div>
        <div className="flex items-center gap-1" role="group" aria-label="Status filters">
          {(['all', 'pass', 'fail', 'exec'] as const).map(filter => (
            <button
              key={filter}
              onClick={() => { setStatusFilter(filter); setCurrentPage(1); }}
              aria-pressed={statusFilter === filter}
              aria-label={`Filter by ${filter} status`}
              className={`flex-1 py-0.5 text-[9px] uppercase font-mono font-bold rounded transition border ${
                statusFilter === filter
                  ? 'bg-[var(--brand-soft)] text-[var(--brand-hover)] border-[var(--brand)]/30'
                  : 'bg-[var(--bg-surface)] text-[var(--text-muted)] hover:text-[var(--text-primary)] border-[var(--border-subtle)]'
              }`}
            >
              {filter}
            </button>
          ))}
        </div>
      </div>

      {/* Runs List */}
      {isLoadingRuns ? (
        <div className="flex-1 flex items-center justify-center py-6 px-3" aria-live="polite">
          <div className="flex flex-col items-center gap-2 text-[var(--text-muted)]">
            <Loader2 className="h-4 w-4 animate-spin text-[var(--brand)]" aria-hidden="true" />
            <span className="text-[10px] font-mono">Loading runs…</span>
          </div>
        </div>
      ) : paginatedRuns.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center p-4 gap-2">
          <div className="h-10 w-10 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-subtle)] flex items-center justify-center text-[var(--text-muted)]">
            <BarChart3 className="h-5 w-5" aria-hidden="true" />
          </div>
          {runHistory.length === 0 ? (
            <>
              <p className="text-[11px] text-[var(--text-muted)] font-medium">No runs recorded yet</p>
              {onOpenLiveBox && (
                <button onClick={onOpenLiveBox} className="btn-primary h-7 px-3 text-[10px] gap-1 mt-1">
                  <Play className="h-3 w-3 fill-current relative z-10" />
                  <span className="relative z-10">Launch First Run</span>
                </button>
              )}
            </>
          ) : (
            <p className="text-[11px] text-[var(--text-muted)]">No runs match this filter</p>
          )}
        </div>
      ) : (
        <div className="flex-1 flex flex-col min-h-0">
          <div className="space-y-1 overflow-y-auto flex-1 px-2 pb-1" role="feed" aria-label="Historical runs">
            {paginatedRuns.map(run => {
              const isPassed = run.status === 'VERIFIED SUCCESS';
              const isFailed = run.status === 'FAILED';
              const borderColor = isPassed ? 'border-l-[var(--success)]' : isFailed ? 'border-l-[var(--danger)]' : 'border-l-[var(--cyan)]';

              return (
                <button
                  key={run.id}
                  onClick={() => {
                    setSelectedRun(run.id);
                    onSetActiveTab?.('overview');
                  }}
                  aria-label={`Run ${run.id}: ${run.issue} — ${run.status}`}
                  className={`w-full text-left p-2.5 rounded-lg border-l-[3px] ${borderColor} border-y border-r border-transparent transition-all duration-200 hover:bg-[var(--bg-hover)] group ${
                    selectedRun === run.id ? 'bg-[var(--brand-soft)]' : ''
                  }`}
                >
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="font-mono text-[10px] font-bold text-[var(--brand-hover)] truncate mr-2">
                      {run.id}
                    </span>
                    <span
                      className={`text-[9px] px-1.5 py-0.2 rounded-full font-mono font-bold uppercase shrink-0 ${
                        isPassed ? 'text-[var(--success)] bg-[var(--success)]/10'
                          : isFailed ? 'text-[var(--danger)] bg-[var(--danger)]/10'
                          : 'text-[var(--cyan)] bg-[var(--cyan)]/10'
                      }`}
                    >
                      {isPassed ? 'PASS' : isFailed ? 'FAIL' : 'EXEC'}
                    </span>
                  </div>
                  <p className="text-[11px] text-[var(--text-primary)] font-sans leading-snug line-clamp-2 group-hover:text-[var(--brand-hover)] transition-colors">
                    {run.issue}
                  </p>
                  <div className="flex items-center gap-3 mt-1.5">
                    <span className="text-[9px] font-mono text-[var(--text-muted)]">
                      {run.cost ? `$${run.cost.toFixed(4)}` : '--'}
                    </span>
                    <span className="text-[9px] font-mono text-[var(--text-muted)]">
                      {run.duration ? `${run.duration.toFixed(1)}s` : '--'}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-2 pt-2 border-t border-[var(--border-subtle)]">
              <button
                onClick={goPrev}
                disabled={currentPage === 1}
                aria-label="Previous page"
                className="p-1 rounded bg-[var(--bg-surface)] hover:bg-[var(--bg-hover)] disabled:opacity-30 transition"
              >
                <ChevronLeft className="h-3 w-3" aria-hidden="true" />
              </button>
              <span className="text-[10px] font-mono text-[var(--text-muted)]">
                {currentPage} / {totalPages}
              </span>
              <button
                onClick={goNext}
                disabled={currentPage === totalPages}
                aria-label="Next page"
                className="p-1 rounded bg-[var(--bg-surface)] hover:bg-[var(--bg-hover)] disabled:opacity-30 transition"
              >
                <ChevronRight className="h-3 w-3" aria-hidden="true" />
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}

function CollapsedRunsRail({
  activeTab,
  setActiveTab,
}: {
  activeTab: LifecycleTab;
  setActiveTab: (id: LifecycleTab) => void;
}) {
  return (
    <div className="flex-1 flex flex-col items-center gap-0.5 py-3 overflow-y-auto">
      {ALL_NAV_ITEMS.map(item => (
        <SidebarNavItem
          key={item.id}
          item={item}
          isActive={activeTab === item.id}
          onClick={() => setActiveTab(item.id)}
          compact
        />
      ))}
    </div>
  );
}
