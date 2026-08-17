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
  Tag,
  ArrowRight,
  CheckCircle2,
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

  if (!isOpen) return null;

  const handleSolve = (issue: GitHubIssue) => {
    const prompt = `[GitHub Issue #${issue.number}] ${issue.title}\n\n${issue.body || ''}`.trim();
    onSelectIssue(prompt);
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-end bg-black/70 backdrop-blur-sm animate-fadeIn"
      role="dialog"
      aria-modal="true"
      aria-labelledby="issues-drawer-title"
    >
      <div
        className="w-full max-w-xl h-full bg-[#0F172A] border-l border-gray-800 shadow-2xl flex flex-col overflow-hidden animate-slideInRight"
        onClick={e => e.stopPropagation()}
      >
        {/* Drawer Header */}
        <div className="p-6 border-b border-gray-800 bg-gradient-to-r from-gray-900 via-[#111827] to-gray-900 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
              <Github className="h-5 w-5" />
            </div>
            <div>
              <h2 id="issues-drawer-title" className="text-base font-bold text-white flex items-center gap-2">
                GitHub Issues Explorer
                <span className="text-[10px] bg-indigo-500/20 text-indigo-400 px-2 py-0.5 rounded-full border border-indigo-500/30 font-mono">
                  {issues.length} open
                </span>
              </h2>
              <p className="text-xs text-gray-400 font-mono truncate max-w-xs">
                {connectedRepo?.fullName || 'Target Repository'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onRefresh}
              disabled={isLoading}
              className="text-gray-400 hover:text-white p-2 rounded-lg hover:bg-gray-800 transition"
              title="Refresh issues"
            >
              <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white p-2 rounded-lg hover:bg-gray-800 transition"
              aria-label="Close drawer"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Search & Label Filters */}
        <div className="p-4 border-b border-gray-800 bg-gray-900/40 space-y-3 shrink-0">
          <div className="relative">
            <Search className="h-4 w-4 text-gray-500 absolute left-3 top-2.5" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Search issues by title, body, or #number..."
              className="w-full bg-gray-950 border border-gray-800 rounded-xl pl-9 pr-4 py-2 text-xs text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          {allLabels.length > 0 && (
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs no-scrollbar">
              <button
                onClick={() => setSelectedLabel(null)}
                className={`px-2.5 py-1 rounded-lg text-[11px] font-medium shrink-0 transition ${
                  selectedLabel === null
                    ? 'bg-indigo-600 text-white font-semibold'
                    : 'bg-gray-900 text-gray-400 hover:text-gray-200 border border-gray-800'
                }`}
              >
                All Labels
              </button>
              {allLabels.map(label => (
                <button
                  key={label.name}
                  onClick={() => setSelectedLabel(selectedLabel === label.name ? null : label.name)}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-medium shrink-0 transition flex items-center gap-1 border ${
                    selectedLabel === label.name
                      ? 'bg-indigo-600/30 text-indigo-300 border-indigo-500 font-semibold'
                      : 'bg-gray-900/60 text-gray-400 hover:text-gray-200 border-gray-800'
                  }`}
                >
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ backgroundColor: `#${label.color}` }}
                  />
                  <span>{label.name}</span>
                  <span className="text-[10px] text-gray-500">({label.count})</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Issues List */}
        <div className="flex-1 p-4 overflow-y-auto space-y-3">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3 text-gray-400 text-xs">
              <Loader2 className="h-6 w-6 animate-spin text-indigo-400" />
              <span>Fetching live open issues from GitHub...</span>
            </div>
          ) : filteredIssues.length === 0 ? (
            <div className="text-center py-16 text-gray-500 text-xs bg-gray-900/30 rounded-2xl border border-gray-800 p-6">
              <AlertCircle className="h-8 w-8 text-gray-600 mx-auto mb-2" />
              <p className="font-semibold text-gray-400">No open issues found</p>
              <p className="text-gray-500 mt-1">Try adjusting your search query or label filters.</p>
            </div>
          ) : (
            filteredIssues.map(issue => (
              <div
                key={issue.id}
                className="bg-gray-900/60 hover:bg-gray-900 border border-gray-800 hover:border-indigo-500/50 rounded-2xl p-4 transition shadow-sm hover:shadow-lg hover:shadow-indigo-500/5 flex flex-col justify-between gap-3 group"
              >
                <div>
                  <div className="flex items-start justify-between gap-2 mb-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-emerald-400 font-mono text-xs font-semibold">
                        #{issue.number}
                      </span>
                      <a
                        href={issue.html_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-gray-500 hover:text-indigo-400 transition"
                        title="View on GitHub"
                      >
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    </div>
                    {issue.comments > 0 && (
                      <span className="flex items-center gap-1 text-[11px] text-gray-400 bg-gray-800 px-2 py-0.5 rounded-full font-mono">
                        <MessageSquare className="h-3 w-3" />
                        {issue.comments}
                      </span>
                    )}
                  </div>

                  <h3 className="text-xs font-bold text-white group-hover:text-indigo-300 transition mb-1 leading-snug">
                    {issue.title}
                  </h3>

                  {issue.body && (
                    <p className="text-[11px] text-gray-400 line-clamp-2 mb-2 font-normal leading-relaxed">
                      {issue.body}
                    </p>
                  )}

                  {issue.labels && issue.labels.length > 0 && (
                    <div className="flex items-center gap-1.5 flex-wrap mt-2">
                      {issue.labels.map(lbl => (
                        <span
                          key={lbl.id}
                          className="text-[10px] px-2 py-0.5 rounded-md font-medium border"
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

                <div className="flex items-center justify-between pt-2 border-t border-gray-800/60 text-[11px] text-gray-500">
                  <span>Opened by @{issue.user.login}</span>
                  <button
                    onClick={() => handleSolve(issue)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white rounded-xl text-xs font-semibold transition shadow-md shadow-indigo-600/20"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
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
