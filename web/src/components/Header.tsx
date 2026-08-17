"use client";

import React, { useState } from 'react';
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
}) => {
  const [showModelDropdown, setShowModelDropdown] = useState(false);

  return (
    <header
      className="border-b border-[var(--border-subtle)] bg-[var(--bg-sidebar)] px-6 py-3 flex items-center justify-between shrink-0 gap-4 flex-wrap z-30"
      role="banner"
    >
      {/* 1. LEFT ZONE: Brand & Harness Subtitle */}
      <div className="flex items-center space-x-3.5">
        <div
          className="h-8 w-8 rounded-lg bg-[var(--brand)] flex items-center justify-center font-bold text-white shadow-sm shrink-0"
          aria-hidden="true"
        >
          <Layers className="h-4 w-4" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold tracking-tight text-[var(--text-primary)] font-mono uppercase">
              LOOM
            </span>
            <span className="text-[10px] bg-[var(--brand-soft)] text-[var(--brand-hover)] px-1.5 py-0.5 rounded border border-[var(--brand)]/30 font-mono">
              HARNESS
            </span>
          </div>
          <p className="text-[11px] text-[var(--text-muted)] tracking-tight">
            Unified Agentic Coding Harness
          </p>
        </div>
      </div>

      {/* 2. CENTER ZONE: Operational Metadata (Repo, Branch, Model) */}
      <div className="flex items-center space-x-2 flex-wrap">
        {/* Target Repository Pill */}
        {onOpenRepoModal && (
          <button
            onClick={onOpenRepoModal}
            className="flex items-center gap-1.5 text-xs bg-[var(--bg-surface)] border border-[var(--border-subtle)] hover:border-[var(--border-default)] px-3 py-1.5 rounded-lg transition text-[var(--text-primary)] group h-8"
            title="Target Repository"
          >
            <FolderGit2 className="h-3.5 w-3.5 text-[var(--text-secondary)] group-hover:text-[var(--brand)] transition shrink-0" />
            <span className="font-mono text-xs max-w-[150px] truncate text-[var(--text-primary)]">
              {connectedRepo?.fullName || 'No Repository Connected'}
            </span>
          </button>
        )}

        {/* Branch Indicator */}
        <div className="flex items-center gap-1 text-xs bg-[var(--bg-surface)] border border-[var(--border-subtle)] px-2.5 py-1.5 rounded-lg text-[var(--text-secondary)] font-mono h-8">
          <GitBranch className="h-3 w-3 text-[var(--success)]" />
          <span>{connectedRepo?.selectedBranch || 'main'}</span>
        </div>

        {/* Active Model Selector Pill */}
        <div className="relative">
          <button
            onClick={() => setShowModelDropdown(!showModelDropdown)}
            className="flex items-center gap-1.5 text-xs bg-[var(--bg-surface)] border border-[var(--border-subtle)] hover:border-[var(--border-default)] px-3 py-1.5 rounded-lg text-[var(--text-primary)] font-mono transition h-8"
            title="Active LLM"
          >
            <Cpu className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
            <span className="max-w-[140px] truncate">{modelName}</span>
            <ChevronDown className="h-3 w-3 text-[var(--text-muted)] ml-0.5" />
          </button>

          {showModelDropdown && (
            <>
              <div className="fixed inset-0 z-30" onClick={() => setShowModelDropdown(false)} />
              <div className="absolute left-0 mt-1.5 w-64 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-xl shadow-2xl z-40 py-1.5 overflow-hidden">
                <div className="px-3 py-1.5 text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-semibold flex items-center justify-between border-b border-[var(--border-subtle)] mb-1">
                  <span>Select Active Model</span>
                  <Link href="/settings/models" className="text-[var(--brand)] hover:underline text-[10px]">
                    Configure
                  </Link>
                </div>
                {availableModels.map(m => (
                  <button
                    key={m}
                    onClick={() => {
                      onModelChange(m);
                      setShowModelDropdown(false);
                    }}
                    className={`w-full text-left px-3 py-1.5 text-xs font-mono transition flex items-center gap-2 ${
                      m === modelName
                        ? 'bg-[var(--brand-soft)] text-[var(--brand-hover)] border-l-2 border-[var(--brand)]'
                        : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] border-l-2 border-transparent'
                    }`}
                  >
                    <Cpu className="h-3 w-3 opacity-60" />
                    <span className="truncate">{m}</span>
                    {m === modelName && (
                      <span className="ml-auto text-[9px] bg-[var(--brand-soft)] text-[var(--brand-hover)] px-1.5 py-0.2 rounded shrink-0">
                        active
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {/* GitHub Issues Trigger */}
        {connectedRepo && onOpenIssuesDrawer && (
          <button
            onClick={onOpenIssuesDrawer}
            className="hidden sm:flex items-center gap-1.5 text-xs text-[var(--text-secondary)] bg-[var(--bg-surface)] border border-[var(--border-subtle)] hover:border-[var(--border-default)] px-3 py-1.5 rounded-lg transition font-medium h-8"
            title="Browse Open GitHub Issues"
          >
            <ListTodo className="h-3.5 w-3.5 text-[var(--brand)]" />
            <span>Issues</span>
          </button>
        )}
      </div>

      {/* 3. RIGHT ZONE: Execution State & Actions */}
      <div className="flex items-center space-x-2.5 flex-wrap">
        {/* System Execution State Indicator */}
        <div className={`status-pill ${isExecuting ? 'status-pill-running' : 'status-pill-success'} h-8`}>
          <Circle className={`h-2 w-2 fill-current ${isExecuting ? 'animate-ping' : ''}`} />
          <span>{isExecuting ? 'EXECUTING' : 'SYSTEM READY'}</span>
        </div>

        {/* Total Runs Count */}
        <div className="status-pill status-pill-idle h-8">
          <span>{runCount} RUNS</span>
        </div>

        {/* Model Settings Link */}
        <Link
          href="/settings/models"
          className="flex items-center justify-center h-8 w-8 text-[var(--text-secondary)] bg-[var(--bg-surface)] border border-[var(--border-subtle)] hover:border-[var(--border-default)] hover:text-[var(--text-primary)] rounded-lg transition"
          title="Model Settings"
        >
          <SettingsIcon className="h-3.5 w-3.5" />
        </Link>

        {/* API Key Modal Button */}
        {onOpenApiKeyModal && (
          <button
            onClick={onOpenApiKeyModal}
            className="flex items-center justify-center h-8 w-8 text-[var(--text-secondary)] bg-[var(--bg-surface)] border border-[var(--border-subtle)] hover:border-[var(--border-default)] hover:text-[var(--text-primary)] rounded-lg transition"
            title="API Keys"
          >
            <Key className="h-3.5 w-3.5" />
          </button>
        )}

        {/* Primary Action Button: Launch Live Box / New Run */}
        <button
          onClick={onOpenLiveBox}
          className="btn-primary h-8 px-3.5 gap-1.5 text-xs shrink-0"
        >
          <Play className="h-3 w-3 fill-current" />
          <span>Open Live Box</span>
        </button>
      </div>
    </header>
  );
};