"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GitPullRequest, ExternalLink, Check, Loader2, AlertCircle, X, Terminal, Sparkles, Play, Pause, RotateCcw, Key } from "lucide-react";
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

  useEffect(() => {
    if (model) setCurrentModel(model);
  }, [model]);

  // PR Creation State
  const [isCreatingPR, setIsCreatingPR] = useState(false);
  const [createdPRUrl, setCreatedPRUrl] = useState<string | null>(null);
  const [prError, setPrError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const logsEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => () => eventSourceRef.current?.close(), []);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView?.({ behavior: 'smooth' });
  }, [logs]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const addLog = useCallback((entry: LogEntry) => {
    setLogs(prev => [...prev, entry]);
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
          setSteps(prev => prev.map(step => step.name === message.step_name ? { ...step, ...data } : step));
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
      } else if (m.includes('openrouter') || m.includes('llama')) {
        providerKey = localStorage.getItem('loom_provider_openrouter_key') || '';
      }
    }

    setError(null);
    setIsRunning(true);
    setStatus("running");
    setLogs([]);
    setPatchDiff(null);
    setCreatedPRUrl(null);
    setPrError(null);
    setSteps(initialSteps.map(step => ({ ...step, status: "pending" })));

    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (loomApiKey) headers["X-API-Key"] = loomApiKey;

      const response = await fetch("/api/run", {
        method: "POST",
        headers,
        body: JSON.stringify({
          issue,
          model: targetModel,
          repo_path: repoPath,
          mock: isMock,
          api_key: loomApiKey || undefined,
          provider_key: providerKey || undefined,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || `Run trigger failed with status ${response.status}`);
      }
      const data = await response.json();
      setRunId(data.run_id);
      startStream(data.run_id);
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : "Failed to start run";
      setIsRunning(false);
      setStatus("failed");
      setError(errMsg);
      addLog({
        timestamp: new Date().toISOString(),
        level: "error",
        agent: "orchestrator",
        message: errMsg,
      });
    }
  };

  const handleAction = async (action: string) => {
    try {
      await sendControl(action);
      if (action === "cancel") {
        setIsRunning(false);
        setStatus("cancelled");
        eventSourceRef.current?.close();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : `Failed to execute ${action}`);
    }
  };

  const handleCreatePullRequest = async () => {
    if (!onCreatePR) return;
    setIsCreatingPR(true);
    setPrError(null);

    try {
      const branchName = `loom-fix-${runId || Date.now()}`;
      const title = `fix: ${issue.slice(0, 70)}${issue.length > 70 ? '...' : ''}`;
      const body = `### Automated Fix by Loom Agentic Harness\n\n**Issue:**\n${issue}\n\n**Model Router:** \`${currentModel || model}\`\n**Run ID:** \`${runId || 'N/A'}\`\n\n### Changes Summary\nUnified patch verified under Sandbox Tier B.\n\n---\n*Generated by Loom Control Plane*`;

      const pr = await onCreatePR({
        title,
        body,
        head: branchName,
      });

      if (pr?.html_url) {
        setCreatedPRUrl(pr.html_url);
      }
    } catch (err: any) {
      setPrError(err.message || 'Failed to create pull request on GitHub');
    } finally {
      setIsCreatingPR(false);
    }
  };

  const getStepModel = (stepName: string, stepModelOverride?: string): string => {
    if (stepModelOverride) return stepModelOverride;
    if (stepName === "onboarding") return "Tree-Sitter AST";
    if (stepName === "verifier") return "Tier B Container";
    if (stepName === "reviewer") return "Proof Layer Auditor";
    return currentModel || model || "Active Model";
  };

  const completed = useMemo(() => steps.filter(step => step.status === "completed").length, [steps]);
  const progress = Math.round((completed / steps.length) * 100);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-md p-4 animate-fadeIn cursor-pointer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="livebox-title"
      onClick={onClose}
    >
      <div
        className="flex h-[88vh] w-[94vw] max-w-6xl flex-col overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--bg-surface)] shadow-2xl cursor-default"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--bg-sidebar)] px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-[var(--brand-soft)] border border-[var(--brand)]/30 flex items-center justify-center text-[var(--brand)]">
              <Terminal className="h-4 w-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="livebox-title" className="text-sm font-bold text-[var(--text-primary)] uppercase font-mono tracking-tight">
                  Live Pipeline Execution
                </h2>
                <span className="status-pill status-pill-idle text-[9px] py-0 px-1.5 font-mono">
                  5-STAGE DAG
                </span>
              </div>
              <p className="mt-0.5 text-xs text-[var(--text-muted)]">Real-time trace stream with state machine preconditions and evidence verification.</p>
            </div>
          </div>
          <button onClick={onClose} className="btn-secondary h-8 px-3 text-xs font-mono">
            Close
          </button>
        </div>

        <div className="grid flex-1 min-h-0 grid-cols-1 gap-4 p-5 lg:grid-cols-3">
          {/* Left Panel: Run Metadata & Control */}
          <section className="min-h-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-4 lg:col-span-1 flex flex-col justify-between overflow-y-auto">
            <div className="space-y-3">
              <div className="flex items-center justify-between font-mono text-xs">
                <span className="text-[var(--text-muted)] font-bold uppercase">RUN ID</span>
                <span className="text-[var(--brand-hover)] font-semibold">{runId || "not started"}</span>
              </div>

              <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-2.5 space-y-1.5 text-xs font-mono">
                <div className="flex items-center justify-between text-[11px] text-[var(--text-muted)]">
                  <span>Repository:</span>
                  <span className="text-[var(--text-primary)] truncate max-w-[170px]" title={repoPath || '.'}>
                    {repoPath || '.'}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[11px] text-[var(--text-muted)] gap-2">
                  <span>Model:</span>
                  {availableModels && availableModels.length > 0 && !isRunning && status === 'idle' ? (
                    <select
                      value={currentModel}
                      onChange={(e) => handleModelSelect(e.target.value)}
                      className="bg-[var(--bg-root)] border border-[var(--border-subtle)] focus:border-[var(--brand)] rounded px-1.5 py-0.5 text-xs text-[var(--cyan)] font-mono outline-none cursor-pointer max-w-[170px] truncate"
                      aria-label="Select execution model"
                    >
                      {availableModels.map(m => (
                        <option key={m} value={m} className="bg-[var(--bg-elevated)] text-[var(--text-primary)] font-mono">
                          {m}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="text-[var(--cyan)] font-bold truncate max-w-[170px]" title={currentModel}>
                      {currentModel}
                    </span>
                  )}
                </div>
                <div className="flex items-center justify-between text-[11px] text-[var(--text-muted)] pt-1.5 border-t border-[var(--border-subtle)]">
                  <span>Execution Mode:</span>
                  <button
                    type="button"
                    onClick={() => !isRunning && setIsMock(!isMock)}
                    disabled={isRunning}
                    className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold transition flex items-center gap-1 cursor-pointer ${
                      isMock
                        ? 'bg-[var(--cyan)]/15 text-[var(--cyan)] border border-[var(--cyan)]/40 hover:bg-[var(--cyan)]/25'
                        : 'bg-[var(--bg-root)] text-[var(--text-muted)] border border-[var(--border-subtle)] hover:text-[var(--text-primary)]'
                    }`}
                  >
                    <span>{isMock ? '⚡ Mock Mode (Simulated)' : '🌐 Real Frontier LLM'}</span>
                  </button>
                </div>
              </div>

              <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-root)] p-3 text-xs text-[var(--text-secondary)] font-mono leading-relaxed max-h-24 overflow-y-auto">
                {issue || "No issue provided"}
              </div>

              <div className="h-1.5 overflow-hidden rounded bg-[var(--bg-root)] border border-[var(--border-subtle)]">
                <div className="h-full bg-[var(--brand)] transition-all duration-300" style={{ width: `${progress}%` }} />
              </div>

              <div className="text-xs text-[var(--text-muted)] font-mono flex items-center justify-between">
                <span>Status: <span className={`font-semibold uppercase ${status === 'completed' ? 'text-[var(--success)]' : status === 'running' ? 'text-[var(--warning)]' : status === 'failed' ? 'text-[var(--danger)]' : 'text-[var(--text-primary)]'}`}>{status}</span></span>
                <span className="text-[11px]">{completed}/{steps.length} steps</span>
              </div>

              <div className="space-y-1.5">
                {steps.map(step => {
                  const stepModel = getStepModel(step.name, step.model);
                  return (
                    <div key={step.name} className="flex items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs font-mono gap-2">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className="text-[var(--text-secondary)] capitalize shrink-0">{step.name}</span>
                        <span className="text-[9px] text-[var(--cyan)] bg-[var(--bg-root)] px-1.5 py-0.2 rounded border border-[var(--border-subtle)] truncate max-w-[100px]" title={stepModel}>
                          {stepModel}
                        </span>
                      </div>
                      <span className={`text-[10px] uppercase font-semibold shrink-0 ${step.status === 'completed' ? 'text-[var(--success)]' : step.status === 'running' ? 'text-[var(--warning)]' : 'text-[var(--text-muted)]'}`}>
                        {step.status}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="pt-3 space-y-2">
              <div className="grid grid-cols-2 gap-2">
                {!isRunning ? (
                  <button onClick={handleStart} disabled={!issue.trim()} className="btn-primary h-8 text-xs font-mono gap-1.5">
                    <Play className="h-3 w-3 fill-current" />
                    <span>Start Run</span>
                  </button>
                ) : (
                  <button onClick={() => handleAction("cancel")} className="btn-secondary h-8 text-xs font-mono text-[var(--danger)] hover:border-[var(--danger)]/50">
                    Cancel
                  </button>
                )}
                <button onClick={() => handleAction("pause")} disabled={!runId || !isRunning} className="btn-secondary h-8 text-xs font-mono">
                  Pause
                </button>
                <button onClick={() => handleAction("resume")} disabled={!runId} className="btn-secondary h-8 text-xs font-mono">
                  Resume
                </button>
                <button onClick={() => handleAction("step")} disabled={!runId} className="btn-secondary h-8 text-xs font-mono">
                  Step
                </button>
              </div>

              {/* GitHub PR Action on Completion */}
              {(status === 'completed' || patchDiff) && onCreatePR && (
                <div className="pt-1">
                  {createdPRUrl ? (
                    <a
                      href={createdPRUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="w-full h-8 bg-[var(--success)]/10 border border-[var(--success)]/30 hover:bg-[var(--success)]/20 text-[var(--success)] rounded-lg text-xs font-mono font-semibold flex items-center justify-center gap-1.5 transition"
                    >
                      <Check className="h-3.5 w-3.5 stroke-[3]" />
                      <span>View PR on GitHub</span>
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  ) : (
                    <button
                      onClick={handleCreatePullRequest}
                      disabled={isCreatingPR}
                      className="btn-primary w-full h-8 text-xs font-mono gap-1.5"
                    >
                      {isCreatingPR ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          <span>Creating PR...</span>
                        </>
                      ) : (
                        <>
                          <GitPullRequest className="h-3.5 w-3.5" />
                          <span>Create GitHub PR</span>
                        </>
                      )}
                    </button>
                  )}
                  {prError && (
                    <p className="text-[10px] text-[var(--danger)] mt-1 flex items-center gap-1 font-mono">
                      <AlertCircle className="h-3 w-3 shrink-0" />
                      <span>{prError}</span>
                    </p>
                  )}
                </div>
              )}

              {error && (
                <div role="alert" className="rounded-lg border border-[var(--danger)]/40 bg-[var(--danger)]/10 p-2.5 text-xs text-[var(--danger)] font-mono space-y-2">
                  <div className="flex items-start gap-1.5">
                    <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                    <span className="leading-tight text-[11px]">{error}</span>
                  </div>
                  {(error.toLowerCase().includes('auth') || error.includes('401') || error.toLowerCase().includes('key') || error.toLowerCase().includes('backend')) && (
                    <div className="flex items-center gap-2 pt-1 border-t border-[var(--danger)]/20 flex-wrap">
                      {onOpenApiKeyModal && (
                        <button
                          type="button"
                          onClick={onOpenApiKeyModal}
                          className="btn-secondary h-6 px-2 text-[10px] gap-1 font-mono text-[var(--text-primary)]"
                        >
                          <Key className="h-2.5 w-2.5 text-[var(--brand)]" />
                          <span>Set Loom API Key</span>
                        </button>
                      )}
                      <a
                        href="/settings/models"
                        className="btn-secondary h-6 px-2 text-[10px] gap-1 font-mono text-[var(--text-primary)]"
                      >
                        <Sparkles className="h-2.5 w-2.5 text-[var(--cyan)]" />
                        <span>Model Settings</span>
                      </a>
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>

          {/* Right Panel: Live Trace Stream & Unified Diff */}
          <section className="min-h-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-4 lg:col-span-2 flex flex-col justify-between">
            <div className="h-[48%] flex flex-col min-h-0">
              <div className="mb-2 text-xs font-mono font-bold uppercase text-[var(--text-muted)] flex items-center justify-between">
                <span>Live Event Stream</span>
                <span className="text-[10px] text-[var(--text-muted)]">{logs.length} events</span>
              </div>
              <div className="flex-1 overflow-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-root)] p-3 font-mono text-[11px]">
                {logs.length === 0 ? <div className="text-[var(--text-muted)] italic">Waiting for backend execution events…</div> : logs.map((log, index) => (
                  <div key={`${log.timestamp}-${index}`} className="mb-1.5">
                    <span className="text-[var(--text-muted)]">{log.timestamp.slice(11, 19)}</span>{" "}
                    <span className="text-[var(--brand-hover)] font-semibold">[{log.agent}]</span>{" "}
                    <span className="text-[var(--text-secondary)]">[{log.level}]</span>{" "}
                    <span className="text-[var(--text-primary)]">{log.message}</span>
                  </div>
                ))}
                <div ref={logsEndRef} />
              </div>
            </div>

            <div className="h-[48%] flex flex-col min-h-0 mt-3">
              <div className="mb-2 text-xs font-mono font-bold uppercase text-[var(--text-muted)] flex items-center justify-between">
                <span>Patch Proposal</span>
                {patchDiff && <span className="status-pill status-pill-verified text-[9px] py-0">UNIFIED DIFF</span>}
              </div>
              <pre className="flex-1 overflow-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-root)] p-3 text-[11px] text-[var(--text-secondary)] font-mono">
                {patchDiff || "No patch event received yet."}
              </pre>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
