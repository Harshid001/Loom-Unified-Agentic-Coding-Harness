"use client";

import React from 'react';
import { Layers, Check, X, AlertCircle } from 'lucide-react';

interface AblationsTabProps {
  displayData: any;
}

const ARCHITECTURE_CONFIGURATIONS = [
  {
    name: 'Full Loom Harness (Tier A-C)',
    memory: true,
    context: true,
    multiAgent: true,
    verification: true,
    passRate: '--',
    cost: '--',
    status: 'Uncalibrated',
  },
  {
    name: 'No 7-Tier Memory Store',
    memory: false,
    context: true,
    multiAgent: true,
    verification: true,
    passRate: '--',
    cost: '--',
    status: 'Uncalibrated',
  },
  {
    name: 'No Context Ranking (TF-IDF/AST)',
    memory: true,
    context: false,
    multiAgent: true,
    verification: true,
    passRate: '--',
    cost: '--',
    status: 'Uncalibrated',
  },
  {
    name: 'Single Agent Baseline (No DAG)',
    memory: false,
    context: false,
    multiAgent: false,
    verification: false,
    passRate: '--',
    cost: '--',
    status: 'Uncalibrated',
  },
];

export const AblationsTab: React.FC<AblationsTabProps> = ({ displayData }) => {
  const hasMeasuredData = Boolean(displayData?.ablations?.length);
  const ablations = hasMeasuredData ? displayData.ablations : ARCHITECTURE_CONFIGURATIONS;

  return (
    <div className="flex-1 loom-card flex flex-col gap-6" id="tabpanel-ablations" role="tabpanel">
      <div className="border-b border-[var(--border-subtle)] pb-3">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono font-bold text-[var(--brand-hover)] bg-[var(--brand-soft)] px-2 py-0.5 rounded border border-[var(--brand)]/30">
            EVALUATION & ABLATIONS
          </span>
          {!hasMeasuredData && (
            <span className="text-[10px] font-mono text-[var(--warning)] bg-[var(--warning-soft)] px-2 py-0.5 rounded border border-[var(--warning)]/30 font-bold">
              CALIBRATION PENDING
            </span>
          )}
        </div>
        <h3 className="text-base font-bold text-[var(--text-primary)] uppercase font-mono mt-1">
          Ablation Experiment Framework
        </h3>
        <p className="text-xs text-[var(--text-muted)] mt-0.5">
          Isolates the architectural delta of Tiered Memory, Context Budget Ranking, and Multi-Agent DAG Orchestration.
        </p>
      </div>

      {!hasMeasuredData && (
        <div className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl flex items-start gap-3 text-xs">
          <AlertCircle className="h-4 w-4 text-[var(--warning)] shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-bold text-[var(--text-primary)] font-mono">
              Empirical Benchmark Run Not Yet Recorded
            </p>
            <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
              Pass rates and cost-per-resolved-issue require executing the evaluation harness against a benchmark suite (e.g. SWE-bench Lite / Verified). The table below reflects the architectural control schema defined in <code className="text-[var(--cyan)] font-mono">loom.telemetry.ablation.AblationHarness</code>.
            </p>
          </div>
        </div>
      )}

      <div className="overflow-x-auto border border-[var(--border-subtle)] rounded-xl">
        <table className="w-full text-left text-xs font-mono">
          <caption className="sr-only">Ablation benchmark metrics across harness features</caption>
          <thead>
            <tr className="bg-[var(--bg-elevated)] border-b border-[var(--border-subtle)] text-[var(--text-muted)] font-semibold uppercase tracking-wider text-[11px]">
              <th scope="col" className="p-3.5">Harness Configuration</th>
              <th scope="col" className="p-3.5 text-center">Tiered Memory</th>
              <th scope="col" className="p-3.5 text-center">Context Ranking</th>
              <th scope="col" className="p-3.5 text-center">Multi-Agent DAG</th>
              <th scope="col" className="p-3.5 text-right">Pass Rate</th>
              <th scope="col" className="p-3.5 text-right">Avg Cost / Run</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border-subtle)] text-[var(--text-secondary)]">
            {ablations.map((ab: any, i: number) => {
              const isFullHarness = ab.name?.includes('Full Loom Harness');
              return (
                <tr
                  key={i}
                  className={
                    isFullHarness
                      ? 'bg-[var(--brand-soft)] text-[var(--text-primary)] font-medium'
                      : 'hover:bg-[var(--bg-hover)] transition'
                  }
                >
                  <td className="p-3.5 flex items-center gap-2 font-sans font-medium text-[var(--text-primary)]">
                    <Layers
                      className={`h-4 w-4 ${isFullHarness ? 'text-[var(--brand)]' : 'text-[var(--text-muted)]'}`}
                      aria-hidden="true"
                    />
                    <span>{ab.name}</span>
                  </td>
                  <td className="p-3.5 text-center">
                    {ab.memory ? (
                      <Check className="h-4 w-4 text-[var(--success)] inline" />
                    ) : (
                      <X className="h-4 w-4 text-[var(--danger)] inline" />
                    )}
                  </td>
                  <td className="p-3.5 text-center">
                    {ab.context ? (
                      <Check className="h-4 w-4 text-[var(--success)] inline" />
                    ) : (
                      <X className="h-4 w-4 text-[var(--danger)] inline" />
                    )}
                  </td>
                  <td className="p-3.5 text-center">
                    {ab.multiAgent ? (
                      <Check className="h-4 w-4 text-[var(--success)] inline" />
                    ) : (
                      <X className="h-4 w-4 text-[var(--danger)] inline" />
                    )}
                  </td>
                  <td className="p-3.5 text-right font-bold text-[var(--text-primary)]">
                    {ab.passRate || '--'}
                  </td>
                  <td className="p-3.5 text-right text-[var(--text-muted)]">
                    {ab.cost || '--'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
