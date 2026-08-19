"use client";

import React, { useEffect, useState, useRef } from 'react';
import { Loader2, Play, GitBranch, FolderGit2, ListTodo, X, Cpu, ChevronDown } from 'lucide-react';

const CHAR_LIMIT = 4000;

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
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [localModel, setLocalModel] = useState(activeModel);
  const modelPickerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { setLocalModel(activeModel); }, [activeModel]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!showModelPicker) return;
    const handleClick = (e: MouseEvent) => {
      if (modelPickerRef.current && !modelPickerRef.current.contains(e.target as Node)) {
        setShowModelPicker(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showModelPicker]);

  const handleModelSelect = (m: string) => {
    setLocalModel(m);
    onModelChange?.(m);
    setShowModelPicker(false);
  };

  const charCount = newIssue.length;
  const charRatio = charCount / CHAR_LIMIT;
  const isOverLimit = charCount > CHAR_LIMIT;

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/80 backdrop-blur-xl flex items-center justify-center p-4 z-50 animate-fade-in"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div className="bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-2xl shadow-2xl shadow-black/50 w-full max-w-xl overflow-hidden animate-slide-in-from-top">
        {/* Header */}
        <div className="relative flex items-center justify-between px-6 pt-5 pb-4 border-b border-[var(--border-subtle)]">
          {/* Top accent line */}
          <div className="absolute top-0 inset-x-0 h-[1px] bg-gradient-to-r from-transparent via-[var(--brand)]/40 to-transparent" aria-hidden="true" />
          <div>
            <span className="text-[10px] font-mono font-bold text-[var(--brand-hover)] bg-[var(--brand-soft)] px-2 py-0.5 rounded border border-[var(--brand)]/30 inline-block mb-1.5">
              PIPELINE EXECUTION
            </span>
            <h2 id="modal-title" className="text-base font-bold text-[var(--text-primary)] font-mono uppercase tracking-tight">
              New Engineering Run
            </h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              What should Loom investigate?
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={isExecuting}
            aria-label="Close dialog"
            className="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition disabled:opacity-40"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {/* Repo / Branch / Model Banner */}
          <div className="flex items-center gap-2 text-xs font-mono text-[var(--text-secondary)] flex-wrap">
            {/* Repo Banner */}
            <div className="flex items-center gap-1.5 bg-[var(--bg-root)] border border-[var(--border-subtle)] px-3 py-1.5 rounded-lg flex-1 min-w-[140px]">
              <FolderGit2 className="h-3.5 w-3.5 text-[var(--brand)] shrink-0" aria-hidden="true" />
              <span className="truncate">{repoName}</span>
            </div>
            <div className="flex items-center gap-1.5 bg-[var(--bg-root)] border border-[var(--border-subtle)] px-3 py-1.5 rounded-lg text-[var(--success)]">
              <GitBranch className="h-3 w-3" aria-hidden="true" />
              <span>{branchName}</span>
            </div>
            {/* Styled Model Selector Pill */}
            <div className="relative" ref={modelPickerRef}>
              <button
                type="button"
                onClick={() => setShowModelPicker(!showModelPicker)}
                disabled={isExecuting}
                aria-haspopup="listbox"
                aria-expanded={showModelPicker}
                aria-label={`Active model: ${localModel}`}
                className="flex items-center gap-1.5 bg-[var(--bg-root)] border border-[var(--border-subtle)] hover:border-[var(--brand)] px-3 py-1.5 rounded-lg text-[var(--cyan)] transition text-xs"
              >
                <Cpu className="h-3.5 w-3.5 text-[var(--cyan)]" aria-hidden="true" />
                <span className="max-w-[140px] truncate">{localModel}</span>
                <ChevronDown className={`h-3 w-3 transition-transform duration-200 ${showModelPicker ? 'rotate-180' : ''}`} aria-hidden="true" />
              </button>
              {showModelPicker && (
                <>
                  <div className="fixed inset-0 z-30" onClick={() => setShowModelPicker(false)} aria-hidden="true" />
                  <div
                    role="listbox"
                    aria-label="Select model"
                    className="absolute left-0 mt-1.5 w-60 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-xl shadow-2xl shadow-black/40 z-40 py-1.5 max-h-64 overflow-y-auto"
                  >
                    {availableModels?.map(m => (
                      <button
                        key={m}
                        role="option"
                        aria-selected={m === localModel}
                        onClick={() => handleModelSelect(m)}
                        className={`w-full text-left px-3 py-1.5 text-xs font-mono transition flex items-center gap-2.5 ${
                          m === localModel
                            ? 'bg-[var(--brand-soft)] text-[var(--brand-hover)] border-l-2 border-[var(--brand)]'
                            : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] border-l-2 border-transparent'
                        }`}
                      >
                        <Cpu className="h-3 w-3 opacity-60 shrink-0" aria-hidden="true" />
                        <span className="truncate">{m}</span>
                        {m === localModel && (
                          <span className="ml-auto text-[9px] bg-[var(--brand-soft)] text-[var(--brand-hover)] px-1.5 py-0.5 rounded font-bold shrink-0">
                            active
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Textarea with character counter */}
          <div>
            <label htmlFor="issue-description-input" className="block text-[11px] font-mono font-bold uppercase text-[var(--text-muted)] mb-1.5 flex items-center gap-1.5">
              <ListTodo className="h-3 w-3 text-[var(--brand)]" aria-hidden="true" />
              Issue Description
              <span className="text-[var(--text-muted)] font-normal normal-case tracking-normal">(describe bug, feature, refactor, or GitHub issue)</span>
            </label>
            <div className="relative">
              <textarea
                ref={textareaRef}
                id="issue-description-input"
                rows={6}
                value={newIssue}
                onChange={(e) => {
                  if (e.target.value.length <= CHAR_LIMIT * 1.5) setNewIssue(e.target.value);
                }}
                placeholder="Describe the bug, feature, refactor, or GitHub issue..."
                aria-required="true"
                className={`w-full bg-[var(--bg-root)] border rounded-xl p-3.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)]/60 focus:outline-none focus:ring-2 font-mono leading-relaxed resize-none transition ${
                  isOverLimit
                    ? 'border-[var(--danger)] focus:border-[var(--danger)] focus:ring-[var(--danger)]/20'
                    : 'border-[var(--border-subtle)] focus:border-[var(--brand)] focus:ring-[var(--brand)]/20'
                }`}
              />
              {/* Character counter */}
              <div className="absolute bottom-2.5 right-3 flex items-center gap-1.5">
                <div className="h-1 w-16 rounded-full bg-[var(--bg-surface)] overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-colors duration-200 ${
                      charRatio > 0.9 ? 'bg-[var(--danger)]' :
                      charRatio > 0.7 ? 'bg-[var(--warning)]' :
                      'bg-[var(--brand)]'
                    }`}
                    style={{ width: `${Math.min(charRatio * 100, 100)}%` }}
                  />
                </div>
                <span className={`text-[9px] font-mono tabular-nums ${isOverLimit ? 'text-[var(--danger)]' : 'text-[var(--text-muted)]'}`}>
                  {charCount}/{CHAR_LIMIT}
                </span>
              </div>
            </div>
          </div>

          {/* Action Controls */}
          <div className="flex items-center justify-between pt-3 border-t border-[var(--border-subtle)]">
            <div>
              {onOpenIssuesDrawer && (
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    onOpenIssuesDrawer();
                  }}
                  disabled={isExecuting}
                  className="btn-secondary h-8 px-3 text-xs gap-1.5"
                >
                  <ListTodo className="h-3.5 w-3.5 text-[var(--brand)]" />
                  <span>Attach Issue</span>
                </button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onClose}
                disabled={isExecuting}
                className="btn-tertiary text-xs"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={onSubmit}
                disabled={isExecuting || !newIssue.trim() || isOverLimit}
                className="btn-primary h-9 px-5 text-xs gap-2 shadow-lg shadow-[var(--brand)]/25"
              >
                {isExecuting ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin relative z-10" />
                    <span className="relative z-10">Launching…</span>
                  </>
                ) : (
                  <>
                    <Play className="h-3.5 w-3.5 fill-current relative z-10" />
                    <span className="relative z-10">Launch Run →</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
