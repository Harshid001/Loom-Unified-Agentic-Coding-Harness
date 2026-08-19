"use client";

import React, { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import {
  Layers,
  Cpu,
  ChevronDown,
  Key,
  GitBranch,
  FolderGit2,
  ListTodo,
  Settings as SettingsIcon,
  Play,
  Circle,
  LogOut,
  Loader2,
  MoreHorizontal,
} from 'lucide-react';
import { Github } from './GithubIcon';
import { ConnectedRepoState, GitHubUser } from '../hooks/useGitHub';

interface HeaderProps {
  modelName: string;
  availableModels: string[];
  onModelChange: (model: string) => void;
  onOpenLiveBox: () => void;
  onOpenApiKeyModal?: () => void;
  onOpenRepoModal?: () => void;
  onOpenIssuesDrawer?: () => void;
  connectedRepo?: ConnectedRepoState | null;
  githubUser?: GitHubUser | null;
  runCount: number;
  isExecuting?: boolean;
  activeRunStage?: string;
  activeRunProgress?: number;
  activeRunTotal?: number;
  activeRunElapsed?: string;
  activeRunId?: string | null;
}

export const Header: React.FC<HeaderProps> = ({
  modelName,
  availableModels,
  onModelChange,
  onOpenLiveBox,
  onOpenApiKeyModal,
  onOpenRepoModal,
  onOpenIssuesDrawer,
  connectedRepo,
  githubUser,
  runCount,
  isExecuting = false,
  activeRunStage = '',
  activeRunProgress = 0,
  activeRunTotal = 5,
  activeRunElapsed = '0:00',
  activeRunId,
}) => {
  const [showModelDropdown, setShowModelDropdown] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [showCtxPopover, setShowCtxPopover] = useState(false);
  const ctxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showCtxPopover) return;
    const handleClick = (e: MouseEvent) => {
      if (ctxRef.current && !ctxRef.current.contains(e.target as Node)) {
        setShowCtxPopover(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showCtxPopover]);

  const handleLogout = async () => {
    if (isLoggingOut) return;
    setIsLoggingOut(true);
    try {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('loom_auth_token');
        sessionStorage.clear();
      }
      await fetch('/api/auth/logout', { method: 'POST' });
    } catch {
      // Fall through to reload
    } finally {
      if (typeof window !== 'undefined') {
        window.location.reload();
      }
    }
  };

  const repoName = connectedRepo?.fullName || 'No Repository Connected';
  const branchName = connectedRepo?.selectedBranch || 'main';

  return (
    <>
    <header
      className="border-b border-[var(--border-subtle)] bg-[var(--bg-sidebar)]/90 backdrop-blur-md px-4 lg:px-6 py-2.5 flex items-center justify-between shrink-0 gap-3 z-30 relative"
      role="banner"
    >
      {/* Subtle animated top-edge glow */}
      <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-[var(--brand)]/30 to-transparent pointer-events-none" aria-hidden="true" />

      {/* ── 1. LEFT ZONE: Brand & Harness Subtitle ── */}
      <div className="flex items-center gap-3 shrink-0">
        {/* Gradient logo with animated ring */}
        <div className="relative group cursor-default">
          <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-[var(--brand)] to-[var(--cyan)] flex items-center justify-center shadow-lg shadow-[var(--brand)]/25 transition-shadow duration-300 group-hover:shadow-[var(--brand)]/50">
            <Layers className="h-4.5 w-4.5 text-white" strokeWidth={2.5} />
          </div>
          {/* Animated ring on hover */}
          <div className="absolute -inset-[3px] rounded-xl border border-[var(--brand)]/0 group-hover:border-[var(--brand)]/60 group-hover:animate-[glow-ring_2s_ease_infinite] transition-all duration-300 pointer-events-none" />
        </div>
        <div className="hidden sm:block">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold tracking-tight text-[var(--text-primary)] font-mono uppercase">
              LOOM
            </span>
            <span className="text-[9px] bg-[var(--brand-soft)] text-[var(--brand-hover)] px-1.5 py-0.5 rounded border border-[var(--brand)]/30 font-mono font-bold">
              HARNESS
            </span>
          </div>
          <p className="text-[10px] text-[var(--text-muted)] tracking-tight leading-none mt-0.5">
            Unified Agentic Coding Harness
          </p>
        </div>
      </div>

      {/* ── 2. CENTER ZONE: Operational Metadata (desktop) ── */}
      <div className="hidden lg:flex items-center gap-1.5">
        {/* Repo Pill */}
        {onOpenRepoModal && (
          <button
            onClick={onOpenRepoModal}
            aria-label={`Target repository: ${repoName}`}
            className="flex items-center gap-1.5 text-xs bg-[var(--bg-surface)] border border-[var(--border-subtle)] hover:border-[var(--border-default)] hover:shadow-[0_0_10px_rgba(124,92,255,0.08)] px-3 py-1.5 rounded-lg transition text-[var(--text-primary)] group h-8"
            title="Target Repository"
          >
            <FolderGit2 className="h-3.5 w-3.5 text-[var(--text-secondary)] group-hover:text-[var(--brand)] transition shrink-0" aria-hidden="true" />
            <span className="font-mono text-xs max-w-[140px] truncate">{repoName}</span>
          </button>
        )}

        {/* Separator */}
        <div className="h-4 w-px bg-[var(--border-subtle)] mx-0.5" aria-hidden="true" />

        {/* Branch Pill */}
        <div
          className="flex items-center gap-1.5 text-xs bg-[var(--bg-surface)] border border-[var(--border-subtle)] px-2.5 py-1.5 rounded-lg text-[var(--text-secondary)] font-mono h-8"
          aria-label={`Current branch: ${branchName}`}
          title="Active Branch"
        >
          <GitBranch className="h-3 w-3 text-[var(--success)]" aria-hidden="true" />
          <span className="max-w-[80px] truncate">{branchName}</span>
        </div>

        {/* Separator */}
        <div className="h-4 w-px bg-[var(--border-subtle)] mx-0.5" aria-hidden="true" />

        {/* Model Selector */}
        <div className="relative">
          <button
            onClick={() => setShowModelDropdown(!showModelDropdown)}
            aria-haspopup="listbox"
            aria-expanded={showModelDropdown}
            aria-label={`Select active model, currently ${modelName}`}
            className="flex items-center gap-1.5 text-xs bg-[var(--bg-surface)] border border-[var(--border-subtle)] hover:border-[var(--border-default)] hover:shadow-[0_0_10px_rgba(124,92,255,0.08)] px-3 py-1.5 rounded-lg text-[var(--text-primary)] font-mono transition h-8"
            title="Active LLM"
          >
            <Cpu className="h-3.5 w-3.5 text-[var(--text-secondary)]" aria-hidden="true" />
            <span className="max-w-[140px] truncate">{modelName}</span>
            <ChevronDown className={`h-3 w-3 text-[var(--text-muted)] ml-0.5 transition-transform duration-200 ${showModelDropdown ? 'rotate-180' : ''}`} aria-hidden="true" />
          </button>

          {showModelDropdown && (
            <>
              <div className="fixed inset-0 z-30" onClick={() => setShowModelDropdown(false)} aria-hidden="true" />
              <div
                className="absolute left-0 mt-2 w-72 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-xl shadow-2xl shadow-black/40 z-40 py-1.5 overflow-hidden"
                role="listbox"
                aria-label="Available models"
              >
                <div className="px-3 py-2 text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-semibold flex items-center justify-between border-b border-[var(--border-subtle)]">
                  <span>Select Active Model</span>
                  <Link href="/settings/models" className="text-[var(--brand)] hover:underline text-[10px]" aria-label="Configure models">
                    Configure
                  </Link>
                </div>
                {availableModels.map(m => (
                  <button
                    key={m}
                    role="option"
                    aria-selected={m === modelName}
                    onClick={() => {
                      onModelChange(m);
                      setShowModelDropdown(false);
                    }}
                    className={`w-full text-left px-3 py-1.5 text-xs font-mono transition flex items-center gap-2.5 ${
                      m === modelName
                        ? 'bg-[var(--brand-soft)] text-[var(--brand-hover)] border-l-2 border-[var(--brand)]'
                        : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] border-l-2 border-transparent'
                    }`}
                  >
                    <Cpu className="h-3 w-3 opacity-60 shrink-0" aria-hidden="true" />
                    <span className="truncate flex-1">{m}</span>
                    {m === modelName && (
                      <span className="text-[9px] bg-[var(--brand-soft)] text-[var(--brand-hover)] px-1.5 py-0.5 rounded font-bold shrink-0">
                        active
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Separator */}
        {connectedRepo && onOpenIssuesDrawer && (
          <>
            <div className="h-4 w-px bg-[var(--border-subtle)] mx-0.5" aria-hidden="true" />
            <button
              onClick={onOpenIssuesDrawer}
              aria-label="Browse open GitHub issues"
              className="flex items-center gap-1.5 text-xs text-[var(--text-secondary)] bg-[var(--bg-surface)] border border-[var(--border-subtle)] hover:border-[var(--border-default)] px-3 py-1.5 rounded-lg transition font-medium h-8 hover:shadow-[0_0_10px_rgba(124,92,255,0.08)]"
              title="Browse Open GitHub Issues"
            >
              <ListTodo className="h-3.5 w-3.5 text-[var(--brand)]" aria-hidden="true" />
              <span>Issues</span>
              {githubUser && (
                <span className="text-[9px] bg-[var(--bg-hover)] text-[var(--text-muted)] px-1.5 py-0.2 rounded-full font-bold">
                  {connectedRepo ? '●' : ''}
                </span>
              )}
            </button>
          </>
        )}
      </div>

      {/* ── 3. RIGHT ZONE: Execution State & Actions ── */}
      <div className="flex items-center gap-2">
        {/* Animated pulse dot + colored ring status indicator */}
        <div
          className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-[11px] font-mono font-bold transition-all duration-300 ${
            isExecuting
              ? 'bg-[rgba(124,92,255,0.12)] border-[rgba(124,92,255,0.5)] text-[var(--cyan)] shadow-[0_0_12px_rgba(124,92,255,0.2)]'
              : 'bg-[rgba(53,213,153,0.08)] border-[rgba(53,213,153,0.3)] text-[var(--success)]'
          }`}
          aria-live="polite"
          aria-label={`System status: ${isExecuting ? 'Executing' : 'System ready'}`}
          title={isExecuting ? 'Pipeline executing…' : 'System ready'}
        >
          <span className="relative flex h-2 w-2">
            <span
              className={`absolute inset-0 rounded-full ${
                isExecuting ? 'bg-[var(--cyan)]' : 'bg-[var(--success)]'
              }`}
              style={{ animation: isExecuting ? 'live-pulse 1.5s ease-in-out infinite' : 'none' }}
            />
            {isExecuting && (
              <span className="absolute inset-0 rounded-full bg-[var(--cyan)]/40 animate-ping" />
            )}
          </span>
          <span className="hidden sm:inline">{isExecuting ? 'EXECUTING' : 'READY'}</span>
        </div>

        {/* Glowing run count bubble */}
        <div
          className="hidden md:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-[var(--bg-surface)] border border-[var(--border-subtle)] text-[11px] font-mono font-bold text-[var(--text-secondary)]"
          aria-label={`${runCount} total runs`}
          title={`${runCount} execution runs recorded`}
        >
          <Play className="h-3 w-3 text-[var(--brand)]" aria-hidden="true" />
          <span className="tabular-nums">{runCount}</span>
          <span className="text-[var(--text-muted)] font-normal">runs</span>
        </div>

        {/* Model Settings */}
        <Link
          href="/settings/models"
          aria-label="Open model settings"
          className="hidden sm:flex items-center justify-center h-8 w-8 text-[var(--text-secondary)] bg-[var(--bg-surface)] border border-[var(--border-subtle)] hover:border-[var(--border-default)] hover:text-[var(--text-primary)] rounded-lg transition"
          title="Model Settings"
        >
          <SettingsIcon className="h-3.5 w-3.5" aria-hidden="true" />
        </Link>

        {/* API Key Modal Button */}
        {onOpenApiKeyModal && (
          <button
            onClick={onOpenApiKeyModal}
            aria-label="Manage API keys"
            className="hidden sm:flex items-center justify-center h-8 w-8 text-[var(--text-secondary)] bg-[var(--bg-surface)] border border-[var(--border-subtle)] hover:border-[var(--border-default)] hover:text-[var(--text-primary)] rounded-lg transition"
            title="API Keys"
          >
            <Key className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        )}

        {/* Logout Button */}
        <button
          onClick={handleLogout}
          disabled={isLoggingOut}
          aria-label="Log out of Loom Dashboard"
          className="hidden sm:flex items-center gap-1.5 h-8 px-2.5 text-xs text-[var(--text-secondary)] bg-[var(--bg-surface)] border border-[var(--border-subtle)] hover:border-[var(--danger)]/50 hover:bg-[var(--danger)]/10 hover:text-[var(--danger)] rounded-lg transition font-mono"
          title="Sign out of Dashboard"
        >
          {isLoggingOut ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--danger)]" aria-hidden="true" />
          ) : (
            <LogOut className="h-3.5 w-3.5 text-[var(--text-muted)] shrink-0" aria-hidden="true" />
          )}
          <span className="hidden lg:inline">Logout</span>
        </button>

        {/* "Open Live Box" primary CTA with shimmer */}
        <button
          onClick={onOpenLiveBox}
          aria-label="Open Live Box execution panel"
          className="btn-primary h-8 px-4 gap-1.5 text-xs shrink-0"
        >
          <Play className="h-3.5 w-3.5 fill-current relative z-10" aria-hidden="true" />
          <span className="relative z-10">Open Live Box</span>
        </button>

        {/* Mobile context popover trigger (lg:hidden) */}
        <div className="lg:hidden relative" ref={ctxRef}>
          <button
            onClick={() => setShowCtxPopover(!showCtxPopover)}
            aria-label="More options"
            aria-expanded={showCtxPopover}
            className="flex items-center justify-center h-8 w-8 text-[var(--text-secondary)] bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-lg transition"
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
          {showCtxPopover && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowCtxPopover(false)} />
              <div className="absolute right-0 top-full mt-2 w-56 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-xl shadow-2xl shadow-black/40 z-50 py-2 space-y-0.5">
                {onOpenRepoModal && (
                  <button onClick={() => { onOpenRepoModal(); setShowCtxPopover(false); }} className="w-full text-left px-3 py-2 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition flex items-center gap-2">
                    <FolderGit2 className="h-3.5 w-3.5 text-[var(--brand)]" aria-hidden="true" />
                    <span className="truncate">{repoName}</span>
                  </button>
                )}
                <div className="px-3 py-1.5 text-[10px] text-[var(--text-muted)] font-mono flex items-center gap-1.5">
                  <GitBranch className="h-3 w-3 text-[var(--success)]" aria-hidden="true" />
                  {branchName}
                </div>
                <div className="px-3 py-1.5 text-[10px] text-[var(--text-muted)] font-mono flex items-center gap-1.5">
                  <Cpu className="h-3.5 w-3.5 text-[var(--cyan)]" aria-hidden="true" />
                  {modelName}
                </div>
                {connectedRepo && onOpenIssuesDrawer && (
                  <button onClick={() => { onOpenIssuesDrawer?.(); setShowCtxPopover(false); }} className="w-full text-left px-3 py-2 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition flex items-center gap-2 border-t border-[var(--border-subtle)] mt-1 pt-2">
                    <ListTodo className="h-3.5 w-3.5 text-[var(--brand)]" aria-hidden="true" />
                    Browse Issues
                  </button>
                )}
                {onOpenApiKeyModal && (
                  <button onClick={() => { onOpenApiKeyModal(); setShowCtxPopover(false); }} className="w-full text-left px-3 py-2 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition flex items-center gap-2">
                    <Key className="h-3.5 w-3.5" aria-hidden="true" />
                    API Keys
                  </button>
                )}
                <Link href="/settings/models" onClick={() => setShowCtxPopover(false)} className="block px-3 py-2 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition flex items-center gap-2">
                  <SettingsIcon className="h-3.5 w-3.5" aria-hidden="true" />
                  Model Settings
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </header>

    {/* ── Live Run Progress Strip ── */}
    {isExecuting && (
      <div className="run-progress-strip" role="status" aria-live="polite" aria-label={`Pipeline executing: Stage ${activeRunProgress}/${activeRunTotal} — ${activeRunStage}`}>
        <span className="relative flex h-2 w-2 shrink-0">
          <span className="absolute inset-0 rounded-full bg-[var(--cyan)] animate-ping opacity-60" />
          <span className="relative rounded-full h-2 w-2 bg-[var(--cyan)]" />
        </span>
        <span className="text-[var(--cyan)] font-bold shrink-0">EXECUTING</span>
        <span className="text-[var(--text-muted)] hidden sm:inline">Stage</span>
        <span className="text-[var(--text-primary)] font-bold">{activeRunProgress}/{activeRunTotal}</span>
        {activeRunStage && (
          <span className="text-[var(--brand-hover)] font-bold">{activeRunStage}</span>
        )}
        <div className="flex-1 max-w-[200px] mx-2">
          <div className="progress-bar-animated" style={{ width: `${(activeRunProgress / activeRunTotal) * 100}%` }} />
        </div>
        <span className="text-[var(--text-muted)] tabular-nums shrink-0">{activeRunElapsed}</span>
        <button
          onClick={onOpenLiveBox}
          className="text-[10px] text-[var(--brand-hover)] hover:underline font-bold ml-auto shrink-0 hidden sm:inline"
        >
          View Live →
        </button>
      </div>
    )}
    </>
  );
};
