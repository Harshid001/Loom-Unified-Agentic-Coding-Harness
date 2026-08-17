"use client";

import React, { useState, useMemo } from 'react';
import {
  X,
  AlertCircle,
  MessageSquare,
  Sparkles,
  Search,
  ExternalLink,
  Loader2,
  RefreshCw,
  ArrowRight,
} from 'lucide-react';
import { Github } from './GithubIcon';
import { GitHubIssue, ConnectedRepoState } from '../hooks/useGitHub';

interface GitHubIssuesDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  connectedRepo: ConnectedRepoState | null;
  issues: GitHubIssue[];
  isLoading: boolean;
  onRefresh: () => void;
  onSelectIssue: (issuePrompt: string) => void;
}

export const GitHubIssuesDrawer: React.FC<GitHubIssuesDrawerProps> = ({
  isOpen,
  onClose,
  connectedRepo,
  issues,
  isLoading,
  onRefresh,
  onSelectIssue,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);

  // Extract unique labels
  const allLabels = useMemo(() => {
    const map = new Map<string, { name: string; color: string; count: number }>();
    issues.forEach(issue => {
      issue.labels?.forEach(label => {
        const existing = map.get(label.name);
        if (existing) {
          existing.count += 1;
        } else {
          map.set(label.name, { name: label.name, color: label.color, count: 1 });
        }
      });
    });
    return Array.from(map.values());
  }, [issues]);

  // Filter issues
  const filteredIssues = useMemo(() => {
    return issues.filter(issue => {
      const matchesSearch =
        issue.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (issue.body && issue.body.toLowerCase().includes(searchQuery.toLowerCase())) ||
        `#${issue.number}`.includes(searchQuery);

      if (!matchesSearch) return false;
      if (selectedLabel && !issue.labels?.some(l => l.name === selectedLabel)) {
        return false;
      }
      return true;
    });
  }, [issues, searchQuery, selectedLabel]);

  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleSolve = (issue: GitHubIssue) => {
    const prompt = `[GitHub Issue #${issue.number}] ${issue.title}\n\n${issue.body || ''}`.trim();
    onSelectIssue(prompt);
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-end bg-black/80 backdrop-blur-sm animate-fadeIn cursor-pointer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="issues-drawer-title"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl h-full bg-[var(--bg-surface)] border-l border-[var(--border-default)] shadow-2xl flex flex-col overflow-hidden animate-slideInRight cursor-default"
        onClick={e => e.stopPropagation()}
      >
        {/* Drawer Header */}
        <div className="p-6 border-b border-[var(--border-subtle)] bg-[var(--bg-sidebar)] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-[var(--brand-soft)] border border-[var(--brand)]/30 flex items-center justify-center text-[var(--brand)]">
              <Github className="h-4 w-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="issues-drawer-title" className="text-sm font-bold text-[var(--text-primary)] uppercase font-mono tracking-tight">
                  GitHub Issues Explorer
                </h2>
                <span className="status-pill status-pill-idle text-[9px] py-0 px-1.5 font-mono">
                  {issues.length} OPEN
                </span>
              </div>
              <p className="text-xs text-[var(--text-muted)] font-mono truncate max-w-xs mt-0.5">
                {connectedRepo?.fullName || 'Target Repository'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              onClick={onRefresh}
              disabled={isLoading}
              className="btn-secondary h-8 w-8 p-0 flex items-center justify-center"
              title="Refresh issues"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="text-[var(--text-muted)] hover:text-[var(--text-primary)] p-1.5 rounded-lg hover:bg-[var(--bg-hover)] transition"
              aria-label="Close drawer"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Search & Label Filters */}
        <div className="p-4 border-b border-[var(--border-subtle)] bg-[var(--bg-elevated)] space-y-2.5 shrink-0">
          <div className="relative">
            <Search className="h-3.5 w-3.5 text-[var(--text-muted)] absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Search issues by title, body, or #number..."
              className="w-full bg-[var(--bg-root)] border border-[var(--border-subtle)] focus:border-[var(--brand)] rounded-lg pl-8 pr-3 py-1.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none font-mono"
            />
          </div>

          {allLabels.length > 0 && (
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs no-scrollbar">
              <button
                onClick={() => setSelectedLabel(null)}
                className={`px-2.5 py-0.5 rounded text-[10px] font-mono font-semibold shrink-0 transition ${
                  selectedLabel === null
                    ? 'bg-[var(--brand)] text-white'
                    : 'bg-[var(--bg-surface)] text-[var(--text-muted)] hover:text-[var(--text-primary)] border border-[var(--border-subtle)]'
                }`}
              >
                All ({issues.length})
              </button>
              {allLabels.map(label => (
                <button
                  key={label.name}
                  onClick={() => setSelectedLabel(selectedLabel === label.name ? null : label.name)}
                  className={`px-2 py-0.5 rounded text-[10px] font-mono shrink-0 transition flex items-center gap-1 border ${
                    selectedLabel === label.name
                      ? 'bg-[var(--brand-soft)] text-[var(--brand-hover)] border-[var(--brand)] font-semibold'
                      : 'bg-[var(--bg-surface)] text-[var(--text-muted)] hover:text-[var(--text-primary)] border-[var(--border-subtle)]'
                  }`}
                >
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ backgroundColor: `#${label.color}` }}
                  />
                  <span>{label.name}</span>
                  <span className="text-[9px] opacity-60">({label.count})</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Issues List */}
        <div className="flex-1 p-4 overflow-y-auto space-y-3">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-2 text-[var(--text-muted)] text-xs font-mono">
              <Loader2 className="h-5 w-5 animate-spin text-[var(--brand)]" />
              <span>Fetching live open issues from GitHub...</span>
            </div>
          ) : filteredIssues.length === 0 ? (
            <div className="text-center py-16 text-[var(--text-muted)] text-xs bg-[var(--bg-elevated)] rounded-xl border border-[var(--border-subtle)] p-6">
              <AlertCircle className="h-6 w-6 text-[var(--text-muted)] mx-auto mb-2" />
              <p className="font-bold text-[var(--text-primary)] font-mono">No open issues found</p>
              <p className="text-[var(--text-secondary)] mt-1">Try adjusting your search query or label filters.</p>
            </div>
          ) : (
            filteredIssues.map(issue => (
              <div
                key={issue.id}
                className="bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)] border border-[var(--border-subtle)] hover:border-[var(--border-default)] rounded-xl p-4 transition flex flex-col justify-between gap-3 group"
              >
                <div>
                  <div className="flex items-start justify-between gap-2 mb-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-[var(--success)] font-mono text-xs font-bold">
                        #{issue.number}
                      </span>
                      <a
                        href={issue.html_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition"
                        title="View on GitHub"
                      >
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    </div>
                    {issue.comments > 0 && (
                      <span className="flex items-center gap-1 text-[10px] text-[var(--text-muted)] bg-[var(--bg-surface)] px-1.5 py-0.2 rounded font-mono border border-[var(--border-subtle)]">
                        <MessageSquare className="h-2.5 w-2.5" />
                        {issue.comments}
                      </span>
                    )}
                  </div>

                  <h3 className="text-xs font-bold text-[var(--text-primary)] group-hover:text-[var(--brand-hover)] transition mb-1 leading-snug font-sans">
                    {issue.title}
                  </h3>

                  {issue.body && (
                    <p className="text-[11px] text-[var(--text-secondary)] line-clamp-2 mb-2 font-normal leading-relaxed">
                      {issue.body}
                    </p>
                  )}

                  {issue.labels && issue.labels.length > 0 && (
                    <div className="flex items-center gap-1.5 flex-wrap mt-2">
                      {issue.labels.map(lbl => (
                        <span
                          key={lbl.id}
                          className="text-[9px] px-1.5 py-0.2 rounded font-mono font-medium border"
                          style={{
                            backgroundColor: `#${lbl.color}15`,
                            color: `#${lbl.color}`,
                            borderColor: `#${lbl.color}40`,
                          }}
                        >
                          {lbl.name}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-[var(--border-subtle)] text-[10px] font-mono text-[var(--text-muted)]">
                  <span>@{issue.user.login}</span>
                  <button
                    onClick={() => handleSolve(issue)}
                    className="btn-primary h-7 px-3 text-xs gap-1.5"
                  >
                    <Sparkles className="h-3 w-3 fill-current" />
                    <span>Solve with Loom</span>
                    <ArrowRight className="h-3 w-3" />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
