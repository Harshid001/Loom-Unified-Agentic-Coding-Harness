"use client";

import React, { useMemo } from 'react';
import {
  BarChart3,
  TrendingUp,
  DollarSign,
  Clock,
  Cpu,
  CheckCircle2,
  XCircle,
  Activity,
} from 'lucide-react';
import { RunItem } from '../hooks/useRuns';

interface AnalyticsTabProps {
  runHistory: RunItem[];
  connectedRepoName?: string;
}

/* ─── SVG Sparkline ─── */
function Sparkline({ data, color, height = 40, width = 200 }: { data: number[]; color: string; height?: number; width?: number }) {
  if (data.length < 2) return null;
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = max - min || 1;
  const step = width / (data.length - 1);

  const points = data.map((v, i) => {
    const x = i * step;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return `${x},${y}`;
  }).join(' ');

  const areaPoints = `0,${height} ${points} ${width},${height}`;

  return (
    <svg width={width} height={height} className="overflow-visible" aria-hidden="true">
      <defs>
        <linearGradient id={`grad-${color.replace(/[^a-z]/gi, '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={areaPoints} fill={`url(#grad-${color.replace(/[^a-z]/gi, '')})`} />
      <polyline points={points} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      {data.map((v, i) => {
        const x = i * step;
        const y = height - ((v - min) / range) * (height - 4) - 2;
        return <circle key={i} cx={x} cy={y} r="2.5" fill={color} className="chart-dot" opacity="0.7" />;
      })}
    </svg>
  );
}

/* ─── Horizontal Bar ─── */
function HBar({ label, value, maxValue, color }: { label: string; value: number; maxValue: number; color: string }) {
  const pct = maxValue > 0 ? (value / maxValue) * 100 : 0;
  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="w-20 text-[var(--text-secondary)] font-mono truncate shrink-0">{label}</span>
      <div className="flex-1 h-3 bg-[var(--bg-surface)] rounded-full overflow-hidden border border-[var(--border-subtle)]">
        <div
          className="chart-bar h-full"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="w-16 text-right font-mono text-[var(--text-muted)] tabular-nums shrink-0">
        {typeof value === 'number' ? (value < 1 ? value.toFixed(4) : value.toFixed(2)) : value}
      </span>
    </div>
  );
}

/* ─── Metric Card ─── */
function MetricCard({ label, value, subtext, icon: Icon, color }: { label: string; value: string; subtext: string; icon: React.ElementType; color: string }) {
  return (
    <div className="chart-container space-y-2">
      <div className="flex items-center gap-2">
        <div className="h-7 w-7 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${color}15`, color }}>
          <Icon className="h-3.5 w-3.5" />
        </div>
        <span className="text-[10px] font-mono font-bold text-[var(--text-muted)] uppercase tracking-wider">{label}</span>
      </div>
      <p className="text-xl font-bold font-mono" style={{ color }}>{value}</p>
      <p className="text-[10px] text-[var(--text-muted)]">{subtext}</p>
    </div>
  );
}

export const AnalyticsTab: React.FC<AnalyticsTabProps> = ({ runHistory, connectedRepoName = 'Workspace' }) => {
  const stats = useMemo(() => {
    const total = runHistory.length;
    const passed = runHistory.filter(r => r.status === 'VERIFIED SUCCESS').length;
    const failed = runHistory.filter(r => r.status === 'FAILED').length;
    const passRate = total > 0 ? (passed / total) * 100 : 0;

    // Cost stats
    const costs = runHistory.filter(r => r.cost && r.cost > 0).map(r => r.cost!);
    const totalCost = costs.reduce((s, c) => s + c, 0);
    const avgCost = costs.length > 0 ? totalCost / costs.length : 0;

    // Duration stats
    const durations = runHistory.filter(r => r.duration && r.duration > 0).map(r => r.duration!);
    const avgDuration = durations.length > 0 ? durations.reduce((s, d) => s + d, 0) / durations.length : 0;

    // Pass rate trend (last N runs in groups of 5)
    const passRateTrend: number[] = [];
    const chunkSize = Math.max(1, Math.floor(total / 10));
    for (let i = 0; i < total; i += chunkSize) {
      const chunk = runHistory.slice(i, i + chunkSize);
      const chunkPass = chunk.filter(r => r.status === 'VERIFIED SUCCESS').length;
      passRateTrend.push(chunk.length > 0 ? (chunkPass / chunk.length) * 100 : 0);
    }

    // Cost trend
    const costTrend = runHistory.slice(-20).map(r => r.cost || 0);

    // Model distribution
    const modelCounts: Record<string, { total: number; passed: number; totalCost: number; totalDuration: number }> = {};
    // We don't have model data per run in RunItem, so we'll show what we can

    return {
      total, passed, failed, passRate,
      totalCost, avgCost, avgDuration,
      passRateTrend, costTrend,
      modelCounts,
    };
  }, [runHistory]);

  // Empty state
  if (runHistory.length === 0) {
    return (
      <div className="loom-card flex flex-col items-center justify-center text-center py-16 gap-4">
        <div className="h-14 w-14 rounded-2xl bg-gradient-to-br from-[var(--brand-soft)] to-[var(--bg-elevated)] border border-[var(--brand)]/30 flex items-center justify-center">
          <BarChart3 className="h-6 w-6 text-[var(--brand)]" />
        </div>
        <h3 className="text-sm font-bold text-[var(--text-primary)] font-mono">No Analytics Data Yet</h3>
        <p className="text-xs text-[var(--text-muted)] max-w-sm">
          Run at least one DAG pipeline execution to start seeing success rates, cost trends, and performance metrics for {connectedRepoName}.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5" id="tabpanel-analytics" role="tabpanel" aria-label="Execution analytics dashboard">
      {/* Header */}
      <div className="loom-card-elevated">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[10px] font-mono font-bold text-[var(--brand-hover)] bg-[var(--brand-soft)] px-2 py-0.5 rounded border border-[var(--brand)]/30">
            ANALYTICS
          </span>
        </div>
        <h2 className="text-base font-bold text-[var(--text-primary)] font-mono uppercase">
          Execution Performance Dashboard
        </h2>
        <p className="text-xs text-[var(--text-muted)] mt-0.5">
          Aggregated metrics across {stats.total} pipeline run{stats.total !== 1 ? 's' : ''} for {connectedRepoName}
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard
          label="Success Rate"
          value={`${stats.passRate.toFixed(1)}%`}
          subtext={`${stats.passed} verified of ${stats.total} total`}
          icon={TrendingUp}
          color="var(--success)"
        />
        <MetricCard
          label="Total Spend"
          value={`$${stats.totalCost.toFixed(4)}`}
          subtext={`Avg $${stats.avgCost.toFixed(4)} per run`}
          icon={DollarSign}
          color="var(--brand)"
        />
        <MetricCard
          label="Avg Duration"
          value={`${stats.avgDuration.toFixed(1)}s`}
          subtext="Time to full verification"
          icon={Clock}
          color="var(--cyan)"
        />
        <MetricCard
          label="Total Runs"
          value={String(stats.total)}
          subtext={`${stats.failed} failed, ${stats.total - stats.passed - stats.failed} executing`}
          icon={Activity}
          color="var(--warning)"
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Pass Rate Trend */}
        <div className="chart-container">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h4 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider font-mono">
                Success Rate Trend
              </h4>
              <p className="text-[10px] text-[var(--text-muted)] mt-0.5">Pass rate over time (grouped)</p>
            </div>
            <div className="flex items-center gap-1.5">
              <CheckCircle2 className="h-3 w-3 text-[var(--success)]" />
              <span className="text-[10px] font-mono text-[var(--success)] font-bold">{stats.passRate.toFixed(0)}%</span>
            </div>
          </div>
          {stats.passRateTrend.length >= 2 ? (
            <Sparkline data={stats.passRateTrend} color="#35D399" width={320} height={60} />
          ) : (
            <p className="text-xs text-[var(--text-muted)] font-mono">Need more runs for trend</p>
          )}
        </div>

        {/* Cost Trend */}
        <div className="chart-container">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h4 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider font-mono">
                Cost per Run
              </h4>
              <p className="text-[10px] text-[var(--text-muted)] mt-0.5">Inference + sandbox cost (last 20 runs)</p>
            </div>
            <div className="flex items-center gap-1.5">
              <DollarSign className="h-3 w-3 text-[var(--brand)]" />
              <span className="text-[10px] font-mono text-[var(--brand)] font-bold">${stats.avgCost.toFixed(4)}</span>
            </div>
          </div>
          {stats.costTrend.length >= 2 ? (
            <Sparkline data={stats.costTrend} color="#7C5CFF" width={320} height={60} />
          ) : (
            <p className="text-xs text-[var(--text-muted)] font-mono">Need more runs for trend</p>
          )}
        </div>
      </div>

      {/* Status Distribution */}
      <div className="chart-container">
        <h4 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider font-mono mb-4">
          Run Status Distribution
        </h4>
        <div className="space-y-2.5">
          <HBar label="VERIFIED" value={stats.passed} maxValue={stats.total} color="#35D399" />
          <HBar label="FAILED" value={stats.failed} maxValue={stats.total} color="#FF5F6D" />
          <HBar label="EXECUTING" value={stats.total - stats.passed - stats.failed} maxValue={stats.total} color="#35D5FF" />
        </div>
      </div>

      {/* Run History Table */}
      <div className="chart-container">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wider font-mono">
            Recent Runs Ledger
          </h4>
          <span className="text-[10px] font-mono text-[var(--text-muted)]">{runHistory.length} total</span>
        </div>
        <div className="overflow-x-auto border border-[var(--border-subtle)] rounded-lg">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="bg-[var(--bg-surface)] border-b border-[var(--border-subtle)] text-[var(--text-muted)] font-mono text-[10px] uppercase">
                <th className="p-2.5">Run ID</th>
                <th className="p-2.5">Status</th>
                <th className="p-2.5">Issue</th>
                <th className="p-2.5 text-right">Cost</th>
                <th className="p-2.5 text-right">Duration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border-subtle)] font-mono text-[11px]">
              {runHistory.slice(0, 20).map((run) => {
                const isPassed = run.status === 'VERIFIED SUCCESS';
                const isFailed = run.status === 'FAILED';
                return (
                  <tr key={run.id} className="hover:bg-[var(--bg-hover)] transition">
                    <td className="p-2.5 text-[var(--brand-hover)] font-bold">{run.id}</td>
                    <td className="p-2.5">
                      <span className={`inline-flex items-center gap-1 ${isPassed ? 'text-[var(--success)]' : isFailed ? 'text-[var(--danger)]' : 'text-[var(--cyan)]'}`}>
                        {isPassed ? <CheckCircle2 className="h-3 w-3" /> : isFailed ? <XCircle className="h-3 w-3" /> : <Activity className="h-3 w-3" />}
                        {isPassed ? 'PASS' : isFailed ? 'FAIL' : 'EXEC'}
                      </span>
                    </td>
                    <td className="p-2.5 text-[var(--text-secondary)] truncate max-w-[200px]">{run.issue}</td>
                    <td className="p-2.5 text-right text-[var(--text-muted)]">{run.cost ? `$${run.cost.toFixed(4)}` : '--'}</td>
                    <td className="p-2.5 text-right text-[var(--text-muted)]">{run.duration ? `${run.duration.toFixed(1)}s` : '--'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
