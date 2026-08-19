"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GitPullRequest, ExternalLink, Check, Loader2, AlertCircle, X, Terminal, Sparkles, Play, Pause, RotateCcw, Key, Copy, TestTube2, FileCode, ShieldCheck, Cpu, CheckCircle2 } from "lucide-react";
import { Github } from "./GithubIcon";

interface LiveBoxProps {
  isOpen: boolean;
  onClose: () => void;
  issue: string;
  model: string;
  repoPath: string;
  mockMode: boolean;
  onRunComplete: (runId: string, success: boolean) => void;
  onCreatePR?: (params: { title: string; body: string; head: string; base?: string }) => Promise<any>;
  hasGitHubToken?: boolean;
  availableModels?: string[];
  onModelChange?: (model: string) => void;
  onOpenApiKeyModal?: () => void;
}

interface StepState {
  name: string;
  status: string;
  model?: string;
  duration?: number;
  cost?: number;
}

interface LogEntry {
  timestamp: string;
  level: string;
  agent: string;
  message: string;
}

const initialSteps: StepState[] = [
  { name: "onboarding", status: "pending" },
  { name: "reproduction", status: "pending" },
  { name: "patcher", status: "pending" },
  { name: "verifier", status: "pending" },
  { name: "reviewer", status: "pending" },
];

  const AGENT_STEP_META: Record<string, { role: string; sandbox: string; auditor: string }> = {
    onboarding:   { role: 'AST Call Graph',        sandbox: 'Tier A Worktree',  auditor: 'Source Mapper' },
    reproduction: { role: 'Failing Test Synthesis', sandbox: 'Tier B Container', auditor: 'Proof Layer Auditor' },
    patcher:      { role: 'Surgical Modification', sandbox: 'Tier B Container', auditor: 'Security Linter' },
    verifier:     { role: 'Regression Verification', sandbox: 'Tier C MicroVM', auditor: 'Proof Layer Auditor' },
    reviewer:     { role: 'Security & Quality Audit', sandbox: 'Tier C MicroVM', auditor: 'Quality Gate' },
  };

  const AGENT_ICONS: Record<string, React.ElementType> = {
    onboarding: Terminal,
    reproduction: TestTube2,
    patcher: FileCode,
    verifier: ShieldCheck,
    reviewer: CheckCircle2,
    system: Cpu,
    stream: Loader2,
  };

export function LiveBoxReal({
  isOpen,
  onClose,
  issue,
  model,
  repoPath,
  mockMode,
  onRunComplete,
  onCreatePR,
  hasGitHubToken,
  availableModels,
  onModelChange,
  onOpenApiKeyModal,
}: LiveBoxProps) {
  const [currentModel, setCurrentModel] = useState<string>(model);
  const [isMock, setIsMock] = useState<boolean>(Boolean(mockMode));
  const [steps, setSteps] = useState<StepState[]>(initialSteps);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [patchDiff, setPatchDiff] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("idle");

  const getStepModel = (stepName: string): string => {
    const active = model || 'gpt-4o';
    if (stepName === 'onboarding') return 'Tree-Sitter AST';
    return active;
  };

  // PR Creation State
  const [isCreatingPR, setIsCreatingPR] = useState(false);
  const [createdPRUrl, setCreatedPRUrl] = useState<string | null>(null);
  const [prError, setPrError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const logsEndRef = useRef<HTMLDivElement | null>(null);
  const logsContainerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => { if (model) setCurrentModel(model); }, [model]);

  useEffect(() => () => eventSourceRef.current?.close(), []);

  // Auto-scroll logs
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView?.({ behavior: "smooth" });
    }
  }, [logs]);

  // Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === "Escape" && !isCreatingPR) onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose, isCreatingPR]);

  const addLog = useCallback((entry: LogEntry) => {
    setLogs(prev => [...prev, entry]);
  }, []);

  const getLogLevelStyles = useCallback((level: string) => {
    switch (level.toLowerCase()) {
      case 'warn':  return 'log-warn';
      case 'error': return 'log-error';
      case 'success':
      case 'ok':    return 'log-success';
      case 'info':
      default:      return level.toLowerCase() === 'system' ? 'log-system' : 'log-info';
    }
  }, []);

  const getStepStatusIcon = useCallback((stepStatus: string, stepName: string) => {
    switch (stepStatus) {
      case "completed": return <Check className="h-3.5 w-3.5 text-[var(--success)]" aria-hidden="true" />;
      case "running":   return <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--cyan)]" aria-hidden="true" />;
      case "failed":    return <AlertCircle className="h-3.5 w-3.5 text-[var(--danger)]" aria-hidden="true" />;
      default:          return <div className="h-2 w-2 rounded-full bg-[var(--border-default)]" aria-hidden="true" />;
    }
  }, []);

  const sendControl = useCallback(async (action: string, payload?: Record<string, any>) => {
    if (!runId) return;
    const loomApiKey = typeof window !== 'undefined' ? (localStorage.getItem('loom_api_key') || localStorage.getItem('loom_auth_token') || '') : '';
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (loomApiKey) headers["X-API-Key"] = loomApiKey;

    const response = await fetch("/api/run/control", {
      method: "POST",
      headers,
      body: JSON.stringify({ run_id: runId, action, ...(payload || {}), api_key: loomApiKey || undefined }),
    });
    if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || `Control action failed: ${action}`);
  }, [runId]);

  const handleModelSelect = useCallback((newModel: string) => {
    setCurrentModel(newModel);
    onModelChange?.(newModel);
    if (runId && isRunning) {
      sendControl("model_switch", { model: newModel }).catch(() => {});
    }
  }, [runId, isRunning, onModelChange, sendControl]);

  const startStream = useCallback((id: string) => {
    eventSourceRef.current?.close();
    const loomApiKey = typeof window !== 'undefined' ? (localStorage.getItem('loom_api_key') || localStorage.getItem('loom_auth_token') || '') : '';
    const streamUrl = loomApiKey
      ? `/api/stream/${encodeURIComponent(id)}?api_key=${encodeURIComponent(loomApiKey)}`
      : `/api/stream/${encodeURIComponent(id)}`;
    const source = new EventSource(streamUrl);
    eventSourceRef.current = source;

    source.onmessage = event => {
      try {
        const message = JSON.parse(event.data);
        const data = message.data || {};
        if (message.type === "log_entry") {
          addLog({
            timestamp: message.timestamp || new Date().toISOString(),
            level: data.level || "info",
            agent: message.step_name || "system",
            message: data.message || "",
          });
        } else if (message.type === "step_progress") {
          setSteps(prev => {
            const next = prev.map(step => step.name === message.step_name ? { ...step, ...data } : step);
            if (next.every(s => s.status === "completed")) {
              setIsRunning(false);
              setStatus("completed");
              onRunComplete(id, true);
            }
            return next;
          });
        } else if (message.type === "patch_generated") {
          setPatchDiff(data.diff || "");
        } else if (message.type === "run_completed") {
          setIsRunning(false);
          const success = Boolean(data.success);
          setStatus(success ? "completed" : "failed");
          onRunComplete(id, success);
          source.close();
        }
      } catch (err) {
        console.error("Failed to parse SSE payload", err);
      }
    };

    source.onerror = () => {
      if (isRunning) {
        addLog({
          timestamp: new Date().toISOString(),
          level: "warn",
          agent: "stream",
          message: "SSE stream connection interrupted. Polling fallback active.",
        });
      }
    };
  }, [addLog, isRunning, onRunComplete]);

  const handleStart = async () => {
    if (!issue.trim()) {
      setError("Issue description is required");
      return;
    }
    const targetModel = currentModel || model;
    const loomApiKey = typeof window !== 'undefined' ? (localStorage.getItem('loom_api_key') || localStorage.getItem('loom_auth_token') || '') : '';
    let providerKey = '';
    if (typeof window !== 'undefined') {
      const m = targetModel.toLowerCase();
      if (m.includes('gemini') || m.includes('google')) {
        providerKey = localStorage.getItem('loom_provider_gemini_key') || '';
      } else if (m.includes('claude') || m.includes('anthropic')) {
        providerKey = localStorage.getItem('loom_provider_anthropic_key') || '';
      } else if (m.includes('gpt') || m.includes('o1') || m.includes('o3') || m.includes('openai')) {
        providerKey = localStorage.getItem('loom_provider_openai_key') || '';
      } else if (m.includes('deepseek')) {
        providerKey = localStorage.getItem('loom_provider_deepseek_key') || '';
      } else if (m.includes('')) {
        providerKey = localStorage.getItem('loom_provider_openrouter_key') || '';
      }
    }

    setError(null);
    setSteps(initialSteps);
    setLogs([]);
    setPatchDiff(null);
    setCreatedPRUrl(null);
    setPrError(null);
    setIsRunning(true);
    setStatus("running");

    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(loomApiKey ? { "X-API-Key": loomApiKey } : {}) },
        body: JSON.stringify({
          issue: issue.trim(),
          model: targetModel,
          repo_path: repoPath,
          mock: isMock,
          api_key: loomApiKey || undefined,
          provider_key: providerKey || undefined,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Run request failed: ${res.status}`);
      }

      const data = await res.json().catch(() => ({}));
      const runIdStr = data.run_id || data.id;
      if (!runIdStr) throw new Error("No run ID returned from server");

      setRunId(runIdStr);
      addLog({
        timestamp: new Date().toISOString(),
        level: "success",
        agent: "system",
        message: `Run ${runIdStr} started on ${targetModel}${isMock ? ' (MOCK)' : ''}`,
      });

      startStream(runIdStr);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start run');
      setIsRunning(false);
      setStatus("idle");
      addLog({
        timestamp: new Date().toISOString(),
        level: "error",
        agent: "system",
        message: `Start failed: ${err instanceof Error ? err.message : 'Unknown error'}`,
      });
    }
  };

  const handleCreatePullRequest = async () => {
    if (!onCreatePR || !runId) return;
    setIsCreatingPR(true);
    setPrError(null);
    try {
      const result = await onCreatePR({
        title: `loom-fix: ${issue.slice(0, 60)}${issue.length > 60 ? '…' : ''}`,
        body: `Automated fix generated by Loom harness\n\nRun ID: ${runId}\nModel: ${currentModel}`,
        head: `loom-fix-${runId.slice(0, 8)}`,
        base: "main",
      });
      setCreatedPRUrl(result?.html_url || result?.url || null);
    } catch {
      setPrError("Failed to create pull request. Check GitHub token.");
    } finally {
      setIsCreatingPR(false);
    }
  };

  const handleAction = async (action: string) => {
    if (!runId) return;
    try {
      await sendControl(action);
      addLog({
        timestamp: new Date().toISOString(),
        level: "info",
        agent: "system",
        message: `Control action "${action}" sent successfully.`,
      });
    } catch {
      addLog({
        timestamp: new Date().toISOString(),
        level: "error",
        agent: "system",
        message: `Control action "${action}" failed.`,
      });
    }
  };

  const copyAllLogs = useCallback(() => {
    const allLogs = logs.map(l => `[${l.timestamp}] [${l.level.toUpperCase()}] [${l.agent}] ${l.message}`).join('\n');
    navigator.clipboard.writeText(allLogs).catch(() => {});
  }, [logs]);

  if (!isOpen) return null;

  const isCompleted = status === "completed" || status === "failed";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Live Box Execution Terminal">
      {/* Backdrop with vignette */}
      <div
        className="absolute inset-0 bg-black/75 backdrop-blur-xl"
        style={{ background: 'radial-gradient(ellipse at center, rgba(8,10,15,0.7) 0%, rgba(8,10,15,0.95) 100%)' }}
        onClick={!isRunning ? onClose : undefined}
        aria-hidden="true"
      />

      {/* Modal Content */}
      <div className="relative w-full max-w-6xl h-[85vh] bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-2xl shadow-2xl shadow-black/50 flex flex-col overflow-hidden">
        {/* Header Bar */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--border-subtle)] shrink-0">
          <div className="flex items-center gap-3">
            <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-[var(--brand)] to-[var(--cyan)] flex items-center justify-center shadow-md shadow-[var(--brand)]/20">
              <Terminal className="h-3.5 w-3.5 text-white" aria-hidden="true" />
            </div>
            <div>
              <h2 className="text-xs font-bold text-[var(--text-primary)] font-mono uppercase">Live Pipeline Execution</h2>
              <p className="text-[10px] text-[var(--text-muted)] font-mono">
                {isRunning ? `Running: ${runId || '…'}` : isCompleted ? `Completed: ${runId || '—'}` : 'Idle'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className={`status-pill ${isRunning ? 'status-pill-running' : isCompleted ? 'status-pill-success' : 'status-pill-idle'} text-[9px]`}>
              {isRunning ? 'EXECUTING' : isCompleted ? 'COMPLETED' : 'READY'}
            </span>
            <button
              onClick={onClose}
              disabled={isRunning}
              aria-label="Close terminal"
              className="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition disabled:opacity-40"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Main 2-col Grid */}
        <div className="flex-1 flex min-h-0">
          {/* LEFT: Controls + Steps */}
          <div className="w-72 border-r border-[var(--border-subtle)] flex flex-col overflow-y-auto shrink-0">
            {/* Issue Card */}
            <div className="p-4 border-b border-[var(--border-subtle)] space-y-2">
              <h3 className="text-[10px] font-mono font-bold text-[var(--text-muted)] uppercase tracking-wider">Issue</h3>
              <p className="text-xs text-[var(--text-secondary)] font-mono leading-relaxed line-clamp-4">{issue || 'No issue specified'}</p>
            </div>

            {/* Model Selector */}
            <div className="p-4 border-b border-[var(--border-subtle)] space-y-2">
              <h3 className="text-[10px] font-mono font-bold text-[var(--text-muted)] uppercase tracking-wider">Model</h3>
              <select
                value={currentModel}
                onChange={e => handleModelSelect(e.target.value)}
                disabled={isRunning}
                aria-label="Select model"
                className="w-full appearance-none bg-[var(--bg-surface)] border border-[var(--border-subtle)] focus:border-[var(--brand)] rounded-lg px-3 py-2 text-xs font-mono text-[var(--text-primary)] outline-none pr-8 cursor-pointer disabled:opacity-50 transition"
              >
                {availableModels?.map(m => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>

            <div className="p-4 border-b border-[var(--border-subtle)] space-y-2">
              <h3 className="text-[10px] font-mono font-bold text-[var(--text-muted)] uppercase tracking-wider">Pipeline Steps</h3>
              <div className="space-y-1.5">
                {steps.map(step => {
                  const statusColor =
                    step.status === 'completed' ? 'border-l-[var(--success)]' :
                    step.status === 'running' ? 'border-l-[var(--cyan)]' :
                    step.status === 'failed' ? 'border-l-[var(--danger)]' : 'border-l-[var(--border-default)]';
                  const meta = AGENT_STEP_META[step.name] || { role: step.name, sandbox: '--', auditor: '--' };
                  const stepModel = step.model || getStepModel(step.name);
                  return (
                    <div
                      key={step.name}
                      className={`p-2.5 rounded-lg border-l-[3px] bg-[var(--bg-surface)] ${statusColor} transition-all duration-300`}
                    >
                      <div className="flex items-center gap-2">
                        {getStepStatusIcon(step.status, step.name)}
                        <div className="flex-1 min-w-0">
                          <p className={`text-[11px] font-mono font-bold capitalize ${step.status === 'completed' ? 'text-[var(--success)]' : step.status === 'running' ? 'text-[var(--cyan)]' : 'text-[var(--text-muted)]'}`}>
                            {step.name}
                          </p>
                          <p className="text-[9px] font-mono text-[var(--text-muted)] truncate">{meta.role}</p>
                        </div>
                      </div>
                      {step.duration && (
                        <p className="text-[9px] font-mono text-[var(--text-muted)] mt-0.5">
                          {(step.duration / 1000).toFixed(1)}s
                        </p>
                      )}
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        <span className="text-[8px] font-mono px-1 py-0.5 rounded bg-[var(--bg-elevated)] text-[var(--cyan)] border border-[var(--border-subtle)]">
                          {stepModel}
                        </span>
                        <span className="text-[8px] font-mono px-1 py-0.5 rounded bg-[var(--bg-elevated)] text-[var(--text-muted)] border border-[var(--border-subtle)]">
                          {meta.sandbox}
                        </span>
                        <span className="text-[8px] font-mono px-1 py-0.5 rounded bg-[var(--bg-elevated)] text-[var(--brand-hover)] border border-[var(--border-subtle)]">
                          {meta.auditor}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Action Buttons */}
            <div className="p-4 space-y-2 mt-auto border-t border-[var(--border-subtle)]">
              {!isRunning && !isCompleted && (
                <button
                  onClick={handleStart}
                  className="btn-primary w-full h-9 text-xs gap-2 shadow-lg shadow-[var(--brand)]/20"
                >
                  <Play className="h-3.5 w-3.5 fill-current relative z-10" />
                  <span className="relative z-10">Start Pipeline</span>
                </button>
              )}
              {isRunning && (
                <div className="grid grid-cols-2 gap-2">
                  <button onClick={() => handleAction("pause")} className="btn-secondary h-8 text-[10px] gap-1">
                    <Pause className="h-3 w-3" aria-hidden="true" /> Pause
                  </button>
                  <button onClick={() => handleAction("cancel")} className="btn-secondary h-8 text-[10px] gap-1 text-[var(--danger)] hover:border-[var(--danger)]/50">
                    <X className="h-3 w-3" aria-hidden="true" /> Cancel
                  </button>
                </div>
              )}
              {isCompleted && (
                <button
                  onClick={handleCreatePullRequest}
                  disabled={isCreatingPR || !hasGitHubToken}
                  className="btn-primary w-full h-9 text-xs gap-2"
                  title={!hasGitHubToken ? 'Connect a GitHub account first' : 'Create pull request'}
                >
                  <GitPullRequest className="h-3.5 w-3.5 relative z-10" aria-hidden="true" />
                  <span className="relative z-10">{isCreatingPR ? 'Creating PR…' : 'Create Pull Request'}</span>
                </button>
              )}
              {error && (
                <div className="flex items-start gap-2 p-2.5 rounded-lg bg-[var(--danger)]/10 border border-[var(--danger)]/30 text-[11px] text-[var(--danger)] font-mono">
                  <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" aria-hidden="true" />
                  <span className="leading-snug">{error}</span>
                </div>
              )}
            </div>
          </div>

          {/* RIGHT: Log Stream + Patch Diff */}
          <div className="flex-1 flex flex-col min-w-0">
            {/* Log Stream */}
            <div className="flex-1 flex flex-col min-h-0">
              <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--border-subtle)] shrink-0">
                <div className="flex items-center gap-2">
                  <h3 className="text-[10px] font-mono font-bold text-[var(--text-muted)] uppercase tracking-wider">Event Stream</h3>
                  {logs.length > 0 && (
                    <span className="text-[9px] font-mono text-[var(--text-muted)] bg-[var(--bg-surface)] px-1.5 py-0.5 rounded-full">
                      {logs.length} entries
                    </span>
                  )}
                </div>
                {logs.length > 0 && (
                  <button onClick={copyAllLogs} aria-label="Copy all logs" className="btn-tertiary text-[10px] gap-1">
                    <Copy className="h-3 w-3" aria-hidden="true" /> Copy All
                  </button>
                )}
              </div>
              <div
                ref={logsContainerRef}
                className="flex-1 overflow-y-auto p-3 space-y-1 font-mono text-xs bg-[var(--bg-root)]"
                role="log"
                aria-label="Live event stream"
              >
                {logs.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-[var(--text-muted)] gap-2 py-8">
                    <Terminal className="h-6 w-6 opacity-30" aria-hidden="true" />
                    <p className="text-[11px]">Waiting for events…</p>
                  </div>
                ) : (
                  logs.map((log, i) => {
                    const time = new Date(log.timestamp).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
                    const levelCls = getLogLevelStyles(log.level);
                    const StepIcon = AGENT_ICONS[log.agent] || Cpu;
                    return (
                      <div key={i} className={`flex items-start gap-2 py-1 px-2 rounded ${levelCls}`}>
                        <span className="text-[var(--text-muted)] shrink-0 select-none tabular-nums text-[10px] pt-0.5">{time}</span>
                        <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded shrink-0 mt-0.5 ${
                          log.level === 'error' ? 'bg-[var(--danger)]/15 text-[var(--danger)]' :
                          log.level === 'warn' ? 'bg-[var(--warning)]/15 text-[var(--warning)]' :
                          log.level === 'success' || log.level === 'ok' ? 'bg-[var(--success)]/15 text-[var(--success)]' :
                          'bg-[var(--brand-soft)] text-[var(--brand-hover)]'
                        }`}>
                          {log.level.toUpperCase()}
                        </span>
                        <span className="text-[var(--text-muted)] shrink-0 text-[10px] mt-0.5 hidden sm:inline">{log.agent}</span>
                        <span className="leading-snug break-all">{log.message}</span>
                      </div>
                    );
                  })
                )}
                <div ref={logsEndRef} />
              </div>
            </div>

            {/* Patch Diff */}
            {patchDiff && (
              <div className="h-48 border-t border-[var(--border-subtle)] flex flex-col shrink-0 animate-slide-in-from-right">
                <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--border-subtle)] shrink-0">
                  <h3 className="text-[10px] font-mono font-bold text-[var(--text-muted)] uppercase tracking-wider">
                    Patch Proposal
                  </h3>
                  <span className="text-[9px] font-mono text-[var(--success)] bg-[var(--success)]/10 px-2 py-0.5 rounded-full font-bold">
                    ✓ Generated
                  </span>
                </div>
                <div className="flex-1 overflow-auto p-3 font-mono text-xs text-[var(--text-secondary)] bg-[var(--bg-root)]">
                  <pre className="whitespace-pre-wrap">{patchDiff}</pre>
                </div>
              </div>
            )}

            {/* PR Result */}
            {(createdPRUrl || prError) && (
              <div className={`shrink-0 p-3 border-t animate-slide-in-from-right ${
                prError ? 'border-[var(--danger)]/40 bg-[var(--danger)]/10' : 'border-[var(--success)]/40 bg-[var(--success)]/10'
              }`}>
                {prError ? (
                  <div className="flex items-start gap-2 text-xs text-[var(--danger)] font-mono">
                    <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
                    <div>
                      <p className="font-bold">PR Creation Failed</p>
                      <p className="text-[var(--text-muted)] mt-0.5">{prError}</p>
                    </div>
                  </div>
                ) : createdPRUrl && (
                  <div className="flex items-center gap-3">
                    <div className="h-6 w-6 rounded-full bg-[var(--success)]/20 flex items-center justify-center text-[var(--success)]">
                      <Check className="h-3.5 w-3.5" aria-hidden="true" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-mono font-bold text-[var(--success)]">Pull Request Created</p>
                      <a
                        href={createdPRUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[11px] text-[var(--brand-hover)] hover:underline font-mono truncate block"
                      >
                        {createdPRUrl}
                      </a>
                    </div>
                    <a
                      href={createdPRUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-secondary h-7 px-2.5 text-[10px] gap-1 shrink-0"
                    >
                      <ExternalLink className="h-3 w-3" aria-hidden="true" />
                      View PR
                    </a>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
