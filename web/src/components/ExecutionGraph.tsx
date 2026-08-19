"use client";

import React from 'react';
import {
  Check,
  Loader2,
  X,
  AlertTriangle,
  ArrowRight,
  Shield,
  FileCode,
  GitBranch,
  Terminal,
  Cpu,
} from 'lucide-react';

export type StageState = 'IDLE' | 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'BLOCKED' | 'SKIPPED' | 'VERIFIED';

export interface ExecutionStage {
  id: string;
  number: string;
  name: string;
  role: string;
  status: StageState;
  duration?: string;
  cost?: string;
  model?: string;
  summary?: string;
}

interface ExecutionGraphProps {
  stages?: ExecutionStage[];
  activeStageId?: string | null;
  onSelectStage?: (stageId: string) => void;
  className?: string;
}

const DEFAULT_STAGES: ExecutionStage[] = [
  {
    id: 'onboarding',
    number: '01',
    name: 'MAPPER',
    role: 'AST Index & Call Graph',
    status: 'IDLE',
    duration: '--',
    cost: '--',
    model: 'Tree-Sitter AST',
    summary: 'Indexes repository workspace and resolves symbol proximity call graphs.',
  },
  {
    id: 'reproduction',
    number: '02',
    name: 'REPRO',
    role: 'Synthesize Failing Test',
    status: 'IDLE',
    duration: '--',
    cost: '--',
    model: 'Active LLM',
    summary: 'Synthesizes deterministic failing test suite validating the target bug (Red phase).',
  },
  {
    id: 'patcher',
    number: '03',
    name: 'PATCH',
    role: 'Surgical Code Modification',
    status: 'IDLE',
    duration: '--',
    cost: '--',
    model: 'Active LLM',
    summary: 'Generates unified code patch modifying only relevant AST subtrees.',
  },
  {
    id: 'verifier',
    number: '04',
    name: 'VERIFY',
    role: 'Sandbox Pytest Suite',
    status: 'IDLE',
    duration: '--',
    cost: '--',
    model: 'Sandbox Tier B',
    summary: 'Executes reproduction and full regression test suite inside isolated sandbox (Green phase).',
  },
  {
    id: 'reviewer',
    number: '05',
    name: 'REVIEW',
    role: 'SHA-256 Evidence Seal',
    status: 'IDLE',
    duration: '--',
    cost: '--',
    model: 'Proof Layer Auditor',
    summary: 'Constructs SHA-256 hash chains across all artifacts and seals execution proof.',
  },
];

export const ExecutionGraph: React.FC<ExecutionGraphProps> = ({
  stages = DEFAULT_STAGES,
  activeStageId,
  onSelectStage,
  className = '',
}) => {
  const getStageIcon = (status: StageState) => {
    switch (status) {
      case 'RUNNING':
        return <Loader2 className="h-3.5 w-3.5 text-[var(--cyan)] animate-spin" />;
      case 'SUCCEEDED':
      case 'VERIFIED':
        return <Check className="h-3.5 w-3.5 text-[var(--success)] stroke-[2.5]" />;
      case 'FAILED':
        return <X className="h-3.5 w-3.5 text-[var(--danger)] stroke-[2.5]" />;
      case 'BLOCKED':
        return <AlertTriangle className="h-3.5 w-3.5 text-[var(--warning)]" />;
      case 'QUEUED':
      case 'IDLE':
      default:
        return <div className="h-2 w-2 rounded-full bg-[var(--text-muted)]" />;
    }
  };

  const getStageStatusClasses = (status: StageState, isSelected: boolean) => {
    if (isSelected) {
      return 'border-[var(--brand)] bg-[var(--brand-soft)]/30 ring-2 ring-[var(--brand)]/70 shadow-[0_0_20px_rgba(124,92,255,0.25)]';
    }
    if (status === 'RUNNING') {
      return 'border-[var(--brand)] bg-[var(--bg-surface)] shadow-[0_0_24px_rgba(124,92,255,0.22)] ring-1 ring-[var(--brand)]/50';
    }
    if (status === 'SUCCEEDED' || status === 'VERIFIED') {
      return 'border-[var(--border-default)] bg-[var(--bg-surface)] hover:border-[var(--success)]/60';
    }
    if (status === 'FAILED') {
      return 'border-[var(--border-default)] bg-[var(--bg-surface)] hover:border-[var(--danger)]/60';
    }
    if (status === 'BLOCKED') {
      return 'border-[var(--warning)]/50 bg-[var(--bg-surface)]';
    }
    // QUEUED / IDLE / SKIPPED
    return 'border-[var(--border-subtle)] bg-[var(--bg-surface)] opacity-80 hover:opacity-100 hover:border-[var(--border-default)]';
  };

  const getStatusTextClass = (status: StageState) => {
    switch (status) {
      case 'RUNNING':
        return 'text-[var(--cyan)]';
      case 'SUCCEEDED':
      case 'VERIFIED':
        return 'text-[var(--success)]';
      case 'FAILED':
        return 'text-[var(--danger)]';
      case 'BLOCKED':
        return 'text-[var(--warning)]';
      case 'QUEUED':
      case 'IDLE':
      default:
        return 'text-[var(--text-muted)]';
    }
  };

  return (
    <div className={`w-full ${className}`}>
      <div className="flex items-center justify-between mb-3 px-1">
        <div className="flex items-center gap-2">
          <div className="h-6 w-6 rounded-lg bg-[var(--brand-soft)] border border-[var(--brand)]/30 flex items-center justify-center">
            <GitBranch className="h-3 w-3 text-[var(--brand)]" />
          </div>
          <h3 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider font-mono">
            5-Stage Execution Graph
          </h3>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="h-1 w-1 rounded-full bg-[var(--text-muted)]" />
          <div className="h-1 w-1 rounded-full bg-[var(--text-muted)]/60" />
          <div className="h-1 w-1 rounded-full bg-[var(--text-muted)]/30" />
          <span className="text-[10px] font-mono text-[var(--text-muted)] ml-1">
            Preconditioned State Machine DAG
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-3 relative">
        {/* Connecting line (desktop only) */}
        <div className="hidden md:block absolute top-[42px] left-[calc(10%+8px)] right-[calc(10%+8px)] h-px bg-gradient-to-r from-[var(--border-subtle)] via-[var(--border-default)] to-[var(--border-subtle)] pointer-events-none" aria-hidden="true" />

        {stages.map((stage, idx) => {
          const isSelected = activeStageId === stage.id;
          const statusClasses = getStageStatusClasses(stage.status, isSelected);
          const statusTextClass = getStatusTextClass(stage.status);

          return (
            <div key={stage.id} className="relative flex flex-col">
              {/* Connector dot (desktop) */}
              <div className="hidden md:flex absolute top-[38px] left-1/2 -translate-x-1/2 z-10 pointer-events-none" aria-hidden="true">
                <div className="h-2 w-2 rounded-full bg-[var(--bg-sidebar)] border border-[var(--border-default)]" />
              </div>

              <button
                onClick={() => onSelectStage?.(stage.id)}
                className={`w-full text-left p-3.5 rounded-xl border transition-all duration-300 ease-out flex flex-col justify-between min-h-[118px] cursor-pointer group ${statusClasses}`}
                aria-label={`Stage ${stage.number}: ${stage.name} - ${stage.status}`}
              >
                {/* Header: Stage Number + Status Badge */}
                <div className="flex items-center justify-between w-full mb-1.5">
                  <span className="text-[10px] font-mono font-bold text-[var(--text-muted)] group-hover:text-[var(--text-secondary)] transition">
                    STAGE {stage.number}
                  </span>
                  <div className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase">
                    {getStageIcon(stage.status)}
                    <span className={statusTextClass}>{stage.status}</span>
                  </div>
                </div>

                {/* Body: Stage Name & Role */}
                <div>
                  <h4 className="text-xs font-bold text-[var(--text-primary)] tracking-wide font-mono mb-0.5">
                    {stage.name}
                  </h4>
                  <p className="text-[11px] text-[var(--text-secondary)] line-clamp-1">
                    {stage.role}
                  </p>
                </div>

                {/* Footer: Telemetry metrics */}
                <div className="flex items-center justify-between text-[10px] font-mono text-[var(--text-muted)] pt-2 border-t border-[var(--border-subtle)] mt-2">
                  <span>{stage.duration || '--'}</span>
                  <span>{stage.cost || '--'}</span>
                </div>
              </button>

              {/* Connecting directional indicator for desktop */}
              {idx < stages.length - 1 && (
                <div className="hidden md:flex absolute -right-2 top-1/2 -translate-y-1/2 z-10 text-[var(--border-default)] pointer-events-none">
                  <ArrowRight className="h-3.5 w-3.5" />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
