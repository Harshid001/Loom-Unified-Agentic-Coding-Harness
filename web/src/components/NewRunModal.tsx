"use client";

import React, { useEffect } from 'react';
import { Loader2, Play, GitBranch, FolderGit2, ListTodo, X, Cpu } from 'lucide-react';

interface NewRunModalProps {
  isOpen: boolean;
  onClose: () => void;
  newIssue: string;
  setNewIssue: (val: string) => void;
  isExecuting: boolean;
  onSubmit: () => void;
  repoName?: string;
  branchName?: string;
  activeModel?: string;
  availableModels?: string[];
  onModelChange?: (model: string) => void;
  onOpenIssuesDrawer?: () => void;
}

export const NewRunModal: React.FC<NewRunModalProps> = ({
  isOpen,
  onClose,
  newIssue,
  setNewIssue,
  isExecuting,
  onSubmit,
  repoName = 'Select Repository',
  branchName = 'main',
  activeModel = 'claude-3-7-sonnet',
  availableModels,
  onModelChange,
  onOpenIssuesDrawer,
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 z-50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div className="bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-xl p-6 max-w-xl w-full shadow-2xl space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-[var(--border-subtle)]">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono font-bold text-[var(--brand-hover)] bg-[var(--brand-soft)] px-2 py-0.5 rounded border border-[var(--brand)]/30">
                PIPELINE EXECUTION
              </span>
            </div>
            <h2 id="modal-title" className="text-base font-bold text-[var(--text-primary)] uppercase font-mono mt-1">
              New Engineering Run
            </h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              What should Loom investigate?
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="text-[var(--text-muted)] hover:text-[var(--text-primary)] p-1 rounded transition"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Target Repo, Branch & Active Model Pills */}
        <div className="flex items-center gap-2 text-xs font-mono text-[var(--text-secondary)] flex-wrap">
          <div className="flex items-center gap-1.5 bg-[var(--bg-surface)] border border-[var(--border-subtle)] px-2.5 py-1 rounded-lg">
            <FolderGit2 className="h-3.5 w-3.5 text-[var(--brand)]" />
            <span>{repoName}</span>
          </div>
          <div className="flex items-center gap-1 bg-[var(--bg-surface)] border border-[var(--border-subtle)] px-2.5 py-1 rounded-lg text-[var(--success)]">
            <GitBranch className="h-3 w-3" />
            <span>{branchName}</span>
          </div>
          <div className="flex items-center gap-1.5 bg-[var(--bg-surface)] border border-[var(--border-subtle)] px-2.5 py-1 rounded-lg text-[var(--cyan)]" title="Target Active Model">
            <Cpu className="h-3.5 w-3.5 text-[var(--cyan)]" />
            <span className="font-bold">{activeModel}</span>
          </div>
        </div>

        {/* Input Area */}
        <div>
          <textarea
            id="issue-description-input"
            rows={5}
            value={newIssue}
            onChange={(e) => setNewIssue(e.target.value)}
            placeholder="Describe the bug, feature, refactor, or GitHub issue..."
            className="w-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] focus:border-[var(--brand)] rounded-lg p-3 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none font-mono leading-relaxed resize-none"
            aria-required="true"
          />
        </div>

        {/* Action Controls */}
        <div className="flex items-center justify-between pt-2 border-t border-[var(--border-subtle)]">
          <div>
            {onOpenIssuesDrawer && (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onOpenIssuesDrawer();
                }}
                className="btn-secondary h-8 px-3 text-xs gap-1.5"
              >
                <ListTodo className="h-3.5 w-3.5 text-[var(--brand)]" />
                <span>Attach Issue</span>
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              disabled={isExecuting}
              className="btn-tertiary text-xs"
            >
              Cancel
            </button>
            <button
              onClick={onSubmit}
              disabled={isExecuting || !newIssue.trim()}
              className="btn-primary h-8 px-4 text-xs gap-1.5"
            >
              {isExecuting ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Launching...</span>
                </>
              ) : (
                <>
                  <Play className="h-3 w-3 fill-current" />
                  <span>Launch Run →</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
