"use client";

import React, { useState } from 'react';
import { GitBranch, Shield, ArrowRight, Play, CheckCircle2, AlertCircle } from 'lucide-react';
import { ExecutionGraph, ExecutionStage } from './ExecutionGraph';

interface DagTabProps {
  displayData: any;
  onOpenLiveBox?: () => void;
}

export const DagTab: React.FC<DagTabProps> = ({ displayData, onOpenLiveBox }) => {
  const [selectedStage, setSelectedStage] = useState<string | null>(null);

  const stages: ExecutionStage[] = [
    {
      id: 'onboarding',
      number: '01',
      name: 'MAPPER',
      role: 'AST Call Graph',
      status: displayData ? (displayData.nodes?.[0]?.status === 'completed' ? 'SUCCEEDED' : 'RUNNING') : 'SUCCEEDED',
      duration: displayData?.nodes?.[0]?.duration || '12.4s',
      cost: displayData?.nodes?.[0]?.cost || '$0.0003',
      model: 'Tree-Sitter AST',
      summary: 'Indexes repository files and resolves symbol proximity call graphs.',
    },
    {
      id: 'reproduction',
      number: '02',
      name: 'REPRO',
      role: 'Failing Test Synthesis',
      status: displayData ? (displayData.nodes?.[1]?.status === 'completed' ? 'SUCCEEDED' : 'RUNNING') : 'SUCCEEDED',
      duration: displayData?.nodes?.[1]?.duration || '31.2s',
      cost: displayData?.nodes?.[1]?.cost || '$0.0008',
      model: 'Claude 3.7 Sonnet',
      summary: 'Synthesizes deterministic failing test suite validating the target bug (Red phase).',
    },
    {
      id: 'patcher',
      number: '03',
      name: 'PATCH',
      role: 'Surgical Code Modification',
      status: displayData ? (displayData.nodes?.[2]?.status === 'completed' ? 'SUCCEEDED' : 'RUNNING') : 'SUCCEEDED',
      duration: displayData?.nodes?.[2]?.duration || '18.7s',
      cost: displayData?.nodes?.[2]?.cost || '$0.0025',
      model: 'Claude 3.7 Sonnet',
      summary: 'Generates unified code patch modifying only relevant AST subtrees.',
    },
    {
      id: 'verifier',
      number: '04',
      name: 'VERIFY',
      role: 'Sandbox Pytest Suite',
      status: displayData ? (displayData.nodes?.[3]?.status === 'completed' ? 'SUCCEEDED' : 'RUNNING') : 'SUCCEEDED',
      duration: displayData?.nodes?.[3]?.duration || '9.1s',
      cost: displayData?.nodes?.[3]?.cost || '$0.0002',
      model: 'Tier B Container',
      summary: 'Executes reproduction and full regression test suite inside isolated sandbox (Green phase).',
    },
    {
      id: 'reviewer',
      number: '05',
      name: 'REVIEW',
      role: 'Evidence Bundle Seal',
      status: displayData ? (displayData.nodes?.[4]?.status === 'completed' ? 'SUCCEEDED' : 'RUNNING') : 'VERIFIED',
      duration: displayData?.nodes?.[4]?.duration || '4.3s',
      cost: displayData?.nodes?.[4]?.cost || '$0.0003',
      model: 'Proof Layer Auditor',
      summary: 'Constructs SHA-256 hash chains across all artifacts and seals execution proof.',
    },
  ];

  return (
    <div className="flex-1 flex flex-col gap-6" id="tabpanel-dag" role="tabpanel">
      {/* Topology Header */}
      <div className="loom-card-elevated flex items-center justify-between flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono font-bold text-[var(--brand-hover)] bg-[var(--brand-soft)] px-2 py-0.5 rounded border border-[var(--brand)]/30">
              DAG TOPOLOGY
            </span>
          </div>
          <h2 className="text-base font-bold text-[var(--text-primary)] uppercase font-mono mt-1">
            5-Stage Autonomous Execution Graph
          </h2>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            Sequential multi-agent execution pipeline with strict state machine preconditions
          </p>
        </div>

        <button
          onClick={onOpenLiveBox}
          className="btn-primary h-8 px-3.5 text-xs gap-1.5"
        >
          <Play className="h-3 w-3 fill-current" />
          <span>Execute Pipeline</span>
        </button>
      </div>

      {/* Signature Execution Graph */}
      <div className="loom-card">
        <ExecutionGraph
          stages={stages}
          activeStageId={selectedStage}
          onSelectStage={setSelectedStage}
        />
      </div>

      {/* Precondition State Machine Matrix */}
      <div className="loom-card">
        <h4 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider font-mono mb-3">
          State Machine Guard Preconditions
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 font-mono text-xs">
          <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg space-y-1">
            <span className="text-[10px] text-[var(--brand-hover)] font-bold">GUARD 01: ONBOARDING</span>
            <p className="text-[var(--text-primary)] font-bold">AST Call Graph Resolution</p>
            <p className="text-[11px] text-[var(--text-muted)] font-sans">
              Repository map and symbol index must resolve successfully before reproduction tests can be synthesized.
            </p>
          </div>

          <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg space-y-1">
            <span className="text-[10px] text-[var(--warning)] font-bold">GUARD 02: REPRODUCTION</span>
            <p className="text-[var(--text-primary)] font-bold">Failing Test Requirement</p>
            <p className="text-[11px] text-[var(--text-muted)] font-sans">
              Reproduction agent must produce a test that fails in the sandbox (exit code 1) before the patcher is unlocked.
            </p>
          </div>

          <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg space-y-1">
            <span className="text-[10px] text-[var(--success)] font-bold">GUARD 03: VERIFICATION</span>
            <p className="text-[var(--text-primary)] font-bold">Green Phase & Integrity Seal</p>
            <p className="text-[11px] text-[var(--text-muted)] font-sans">
              Pytest suite must pass completely and hash chains must validate before run status is marked VERIFIED SUCCESS.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};