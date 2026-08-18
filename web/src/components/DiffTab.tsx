"use client";

import React from 'react';
import { FileCode, Play, Copy, Check } from 'lucide-react';

interface DiffTabProps {
  displayData: any;
  onOpenLiveBox?: () => void;
}

export const DiffTab: React.FC<DiffTabProps> = ({ displayData, onOpenLiveBox }) => {
  const [copied, setCopied] = React.useState(false);

  if (!displayData) {
    return (
      <div className="flex-1 loom-card flex flex-col items-center justify-center text-center gap-4 py-16">
        <div className="h-12 w-12 rounded-xl bg-[var(--brand-soft)] border border-[var(--brand)]/30 flex items-center justify-center text-[var(--brand)]">
          <FileCode className="h-6 w-6" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-[var(--text-primary)] font-mono mb-1">
            No Verified Patch Selected
          </h3>
          <p className="text-xs text-[var(--text-muted)] max-w-md">
            When an autonomous run executes, Loom&apos;s Patcher agent synthesizes a surgical code diff, verifies it in an isolated sandbox, and renders it here with unified syntax additions and deletions.
          </p>
        </div>
        <button
          onClick={onOpenLiveBox}
          aria-label="Launch run to generate verified patch"
          className="btn-primary gap-1.5"
        >
          <Play className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
          <span>Launch Run to Generate Patch</span>
        </button>
      </div>
    );
  }

  const patchDiff = displayData.patchDiff || '';
  const diffLines = patchDiff.split('\n');

  const handleCopy = () => {
    navigator.clipboard.writeText(patchDiff);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex-1 loom-card flex flex-col gap-4" id="tabpanel-diff" role="tabpanel" aria-label="Verified unified patch diff viewer">
      <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider font-mono">
              Verified Unified Patch Diff
            </h3>
            <span className="status-pill status-pill-verified text-[10px]">
              VALIDATED
            </span>
          </div>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            Surgical code modification validated by test harness execution
          </p>
        </div>

        <button
          onClick={handleCopy}
          aria-label={copied ? "Patch diff copied to clipboard" : "Copy patch diff to clipboard"}
          className="btn-secondary h-8 px-3 text-xs gap-1.5"
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5 text-[var(--success)]" aria-hidden="true" />
              <span>Copied Diff</span>
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Copy Diff</span>
            </>
          )}
        </button>
      </div>

      <div className="bg-[var(--bg-root)] border border-[var(--border-subtle)] rounded-xl p-4 font-mono text-xs overflow-x-auto flex-1 text-[var(--text-secondary)] space-y-1">
        {diffLines.map((line: string, i: number) => {
          let colorClass = 'text-[var(--text-secondary)]';
          if (line.startsWith('+') && !line.startsWith('+++'))
            colorClass = 'text-[var(--success)] bg-[var(--success)]/10 px-1 rounded';
          else if (line.startsWith('-') && !line.startsWith('---'))
            colorClass = 'text-[var(--danger)] bg-[var(--danger)]/10 px-1 rounded';
          else if (line.startsWith('@@'))
            colorClass = 'text-[var(--brand-hover)] font-bold';
          else if (line.startsWith('---') || line.startsWith('+++'))
            colorClass = 'text-[var(--text-muted)] font-semibold';

          return (
            <div key={i} className={`flex items-start gap-4 ${colorClass}`}>
              <span className="text-[var(--text-muted)] select-none w-8 text-right font-mono text-[11px]">
                {i + 1}
              </span>
              <pre className="font-mono whitespace-pre-wrap">{line}</pre>
            </div>
          );
        })}
      </div>
    </div>
  );
};
