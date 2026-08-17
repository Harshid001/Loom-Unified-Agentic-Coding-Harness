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
    status: 'SUCCEEDED',
    duration: '12.4s',
    cost: '$0.0003',
    model: 'Tree-Sitter AST',
    summary: 'Generated symbol graph with 142 functions and ranked TF-IDF proximity tokens.',
  },
  {
    id: 'reproduction',
    number: '02',
    name: 'REPRO',
    role: 'Synthesize Failing Test',
    status: 'SUCCEEDED',
    duration: '31.2s',
    cost: '$0.0008',
    model: 'Claude 3.7 Sonnet',
    summary: 'Generated reproduction test case asserting expected bug behavior (Red phase).',
  },
  {
    id: 'patcher',
    number: '03',
    name: 'PATCH',
    role: 'Surgical Code Modification',
    status: 'RUNNING',
    duration: '18.7s',
    cost: '$0.0025',
    model: 'Claude 3.7 Sonnet',
    summary: 'Generating unified patch diff across 4 impacted files within budget limits.',
  },
  {
    id: 'verifier',
    number: '04',
    name: 'VERIFY',
    role: 'Sandbox Pytest Suite',
    status: 'QUEUED',
    duration: '--',
    cost: '--',
    model: 'Sandbox Tier A/B',
    summary: 'Awaiting patch candidate for execution in isolated container.',
  },
  {
    id: 'reviewer',
    number: '05',
    name: 'REVIEW',
    role: 'SHA-256 Evidence Seal',
    status: 'QUEUED',
    duration: '--',
    cost: '--',
    model: 'Proof Layer Hash Chain',
    summary: 'Awaiting verification pass to compute cryptographic hash chain bundle.',
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
    if (status === 'RUNNING') {
      return 'border-[var(--brand)] bg-[var(--bg-surface)] shadow-[0_0_24px_rgba(124,92,255,0.22)] ring-1 ring-[var(--brand)]/50';
    }
    if (status === 'SUCCEEDED' || status === 'VERIFIED') {
      return isSelected
        ? 'border-[var(--success)] bg-[var(--bg-surface)] ring-1 ring-[var(--success)]/40'
        : 'border-[var(--border-default)] bg-[var(--bg-surface)] hover:border-[var(--success)]/60';
    }
    if (status === 'FAILED') {
      return isSelected
        ? 'border-[var(--danger)] bg-[var(--bg-surface)] ring-1 ring-[var(--danger)]/40'
        : 'border-[var(--border-default)] bg-[var(--bg-surface)] hover:border-[var(--danger)]/60';
    }
    if (status === 'BLOCKED') {
      return 'border-[var(--warning)]/50 bg-[var(--bg-surface)]';
    }
    // QUEUED / IDLE / SKIPPED
    return 'border-[var(--border-subtle)] bg-[var(--bg-surface)] opacity-70 hover:opacity-100 hover:border-[var(--border-default)]';
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
          <GitBranch className="h-4 w-4 text-[var(--brand)]" />
          <h3 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider font-mono">
            5-Stage Execution Graph
          </h3>
        </div>
        <span className="text-[11px] font-mono text-[var(--text-muted)]">
          Preconditioned State Machine DAG
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-3 relative">
        {stages.map((stage, idx) => {
          const isSelected = activeStageId === stage.id;
          const statusClasses = getStageStatusClasses(stage.status, isSelected);
          const statusTextClass = getStatusTextClass(stage.status);

          return (
            <div key={stage.id} className="relative flex flex-col">
              <button
                onClick={() => onSelectStage?.(stage.id)}
                className={`w-full text-left p-3.5 rounded-xl border transition flex flex-col justify-between min-h-[118px] cursor-pointer group ${statusClasses}`}
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
