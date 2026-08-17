"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GitPullRequest, ExternalLink, Check, Loader2, AlertCircle } from "lucide-react";
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
}

interface StepState {
  name: string;
  status: string;
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
}: LiveBoxProps) {
  const [steps, setSteps] = useState<StepState[]>(initialSteps);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [patchDiff, setPatchDiff] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("idle");

  // PR Creation State
  const [isCreatingPR, setIsCreatingPR] = useState(false);
  const [createdPRUrl, setCreatedPRUrl] = useState<string | null>(null);
  const [prError, setPrError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => () => eventSourceRef.current?.close(), []);

  const addLog = useCallback((entry: LogEntry) => {
    setLogs(prev => [...prev, entry]);
  }, []);

  const sendControl = useCallback(async (action: string) => {
    if (!runId) return;
    const response = await fetch("/api/run/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId, action }),
    });
    if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || `Control action failed: ${action}`);
  }, [runId]);

  const startStream = useCallback((id: string) => {
    eventSourceRef.current?.close();
    const source = new EventSource(`/api/stream/${encodeURIComponent(id)}`);
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
        } else if (message.type === "patch_proposal") {
          setPatchDiff(data.diff || null);
        } else if (message.type === "status_change") {
          const nextStatus = data.status || "unknown";
          setStatus(nextStatus);
          if (["completed", "failed", "security_hold", "rolled_back"].includes(nextStatus)) {
            setIsRunning(false);
            source.close();
            onRunComplete(id, nextStatus === "completed");
          }
        }
      } catch {
        addLog({ timestamp: new Date().toISOString(), level: "error", agent: "stream", message: "Received invalid SSE payload" });
      }
    };

    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) {
        setIsRunning(false);
      }
    };
  }, [addLog, onRunComplete]);

  const handleStart = useCallback(async () => {
    if (!issue.trim() || isRunning) return;
    setError(null);
    setLogs([]);
    setSteps(initialSteps);
    setPatchDiff(null);
    setStatus("starting");
    setRunId(null);
    setIsRunning(true);
    setCreatedPRUrl(null);
    setPrError(null);

    try {
      const response = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          issue,
          model,
          repo_path: repoPath,
          mock: mockMode,
          async_mode: true,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `Run creation failed (${response.status})`);
      if (!data.run_id) throw new Error("Backend accepted the request but returned no run_id");
      setRunId(data.run_id);
      setStatus("running");
      startStream(data.run_id);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown execution error";
      setError(message);
      setStatus("failed");
      setIsRunning(false);
      onRunComplete("", false);
    }
  }, [issue, isRunning, mockMode, model, onRunComplete, repoPath, startStream]);

  const handleAction = useCallback(async (action: string) => {
    try {
      await sendControl(action);
      setStatus(action);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Control action failed");
    }
  }, [sendControl]);

  const handleCreatePullRequest = async () => {
    if (!onCreatePR) return;
    setIsCreatingPR(true);
    setPrError(null);
    try {
      const branchName = `loom/fix-${runId || Date.now().toString(36)}`;
      const prTitle = `Loom Automated Fix: ${issue.slice(0, 72)}`;
      const prBody = `## Automated Fix by Loom Agentic Harness\n\n### Target Issue\n${issue}\n\n### Run ID\n\`${runId}\`\n\n### Verification\n- Status: \`${status}\`\n- Model: \`${model}\``;

      const res = await onCreatePR({
        title: prTitle,
        body: prBody,
        head: branchName,
      });

      if (res && res.html_url) {
        setCreatedPRUrl(res.html_url);
      } else {
        setCreatedPRUrl(`https://github.com/${repoPath}/pull/new/${branchName}`);
      }
    } catch (err: any) {
      setPrError(err.message || 'Failed to create Pull Request');
    } finally {
      setIsCreatingPR(false);
    }
  };

  const completed = useMemo(() => steps.filter(step => step.status === "completed").length, [steps]);
  const progress = Math.round((completed / steps.length) * 100);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4" role="dialog" aria-modal="true" aria-labelledby="livebox-title">
      <div className="flex h-[88vh] w-[94vw] max-w-6xl flex-col overflow-hidden rounded-2xl border border-slate-800 bg-[#090D16] shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <div>
            <h2 id="livebox-title" className="text-sm font-semibold text-white flex items-center gap-2">
              Live Pipeline Execution
              <span className="text-[10px] bg-indigo-500/20 text-indigo-400 px-2 py-0.5 rounded-full border border-indigo-500/30">
                5-Stage DAG
              </span>
            </h2>
            <p className="mt-0.5 text-xs text-slate-400">Real-time trace stream with state machine preconditions and evidence verification.</p>
          </div>
          <button onClick={onClose} className="rounded-lg border border-slate-700 px-3.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800 transition">
            Close
          </button>
        </div>

        <div className="grid flex-1 min-h-0 grid-cols-1 gap-4 p-5 lg:grid-cols-3">
          <section className="min-h-0 rounded-xl border border-slate-800 bg-slate-950/40 p-4 lg:col-span-1 flex flex-col justify-between">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-300">Run</span>
                <span className="text-xs font-mono text-indigo-400">{runId || "not started"}</span>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-2.5 space-y-1.5 text-xs">
                <div className="flex items-center justify-between text-[11px] text-slate-400">
                  <span>Repository:</span>
                  <span className="font-mono text-indigo-300 truncate max-w-[170px]" title={repoPath || '.'}>
                    {repoPath || '.'}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[11px] text-slate-400">
                  <span>Model:</span>
                  <span className="font-mono text-emerald-400">{model}</span>
                </div>
              </div>
              <div className="rounded-lg border border-slate-800 p-3 text-xs text-slate-200 font-mono leading-relaxed max-h-24 overflow-y-auto">
                {issue || "No issue provided"}
              </div>
              <div className="h-2 overflow-hidden rounded bg-slate-800">
                <div className="h-full bg-indigo-500 transition-all duration-300" style={{ width: `${progress}%` }} />
              </div>
              <div className="text-xs text-slate-400 flex items-center justify-between">
                <span>Status: <span className={`font-semibold uppercase text-xs ${status === 'completed' ? 'text-emerald-400' : status === 'running' ? 'text-amber-400' : status === 'failed' ? 'text-red-400' : 'text-slate-300'}`}>{status}</span></span>
                <span className="font-mono text-[11px] text-slate-500">{completed}/{steps.length} steps</span>
              </div>
              <div className="space-y-1.5">
                {steps.map(step => (
                  <div key={step.name} className="flex items-center justify-between rounded-lg border border-slate-800 px-3 py-1.5 text-xs">
                    <span className="text-slate-300 capitalize">{step.name}</span>
                    <span className={`font-mono text-[11px] ${step.status === 'completed' ? 'text-emerald-400' : step.status === 'running' ? 'text-amber-400' : 'text-slate-500'}`}>
                      {step.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="pt-3 space-y-2">
              <div className="grid grid-cols-2 gap-2">
                {!isRunning ? (
                  <button onClick={handleStart} disabled={!issue.trim()} className="rounded-lg bg-indigo-600 hover:bg-indigo-500 px-3 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40 transition">
                    Start real run
                  </button>
                ) : (
                  <button onClick={() => handleAction("cancel")} className="rounded-lg bg-rose-600 hover:bg-rose-500 px-3 py-2 text-xs font-semibold text-white transition">
                    Cancel
                  </button>
                )}
                <button onClick={() => handleAction("pause")} disabled={!runId || !isRunning} className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 disabled:opacity-40 hover:bg-slate-800 transition">
                  Pause
                </button>
                <button onClick={() => handleAction("resume")} disabled={!runId} className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 disabled:opacity-40 hover:bg-slate-800 transition">
                  Resume
                </button>
                <button onClick={() => handleAction("step")} disabled={!runId} className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 disabled:opacity-40 hover:bg-slate-800 transition">
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
                      className="w-full py-2 bg-emerald-600/20 border border-emerald-500/40 hover:bg-emerald-600/30 text-emerald-300 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition"
                    >
                      <Check className="h-3.5 w-3.5" />
                      <span>View Pull Request on GitHub</span>
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  ) : (
                    <button
                      onClick={handleCreatePullRequest}
                      disabled={isCreatingPR}
                      className="w-full py-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition shadow-lg shadow-purple-600/20 disabled:opacity-50"
                    >
                      {isCreatingPR ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          <span>Creating Pull Request...</span>
                        </>
                      ) : (
                        <>
                          <GitPullRequest className="h-3.5 w-3.5" />
                          <span>Create GitHub Pull Request</span>
                        </>
                      )}
                    </button>
                  )}
                  {prError && (
                    <p className="text-[10px] text-rose-400 mt-1 flex items-center gap-1">
                      <AlertCircle className="h-3 w-3 shrink-0" />
                      <span>{prError}</span>
                    </p>
                  )}
                </div>
              )}

              {mockMode && <p className="rounded-lg border border-amber-900/60 bg-amber-950/30 p-2 text-[11px] text-amber-300">Mock mode enabled. Production runtime guards reject mock execution.</p>}
              {error && <p role="alert" className="rounded-lg border border-rose-900/60 bg-rose-950/30 p-2 text-[11px] text-rose-300">{error}</p>}
            </div>
          </section>

          <section className="min-h-0 rounded-xl border border-slate-800 bg-slate-950/40 p-4 lg:col-span-2 flex flex-col justify-between">
            <div className="h-[48%] flex flex-col min-h-0">
              <div className="mb-2 text-xs font-medium text-slate-300 flex items-center justify-between">
                <span>Live Event Stream</span>
                <span className="text-[10px] text-slate-500 font-mono">{logs.length} events</span>
              </div>
              <div className="flex-1 overflow-auto rounded-lg border border-slate-800 bg-black/20 p-3 font-mono text-[11px]">
                {logs.length === 0 ? <div className="text-slate-600">Waiting for backend events…</div> : logs.map((log, index) => (
                  <div key={`${log.timestamp}-${index}`} className="mb-1.5">
                    <span className="text-slate-600">{log.timestamp.slice(11, 19)}</span> <span className="text-indigo-300">[{log.agent}]</span> <span className="text-slate-400">[{log.level}]</span> {log.message}
                  </div>
                ))}
              </div>
            </div>

            <div className="h-[48%] flex flex-col min-h-0 mt-3">
              <div className="mb-2 text-xs font-medium text-slate-300 flex items-center justify-between">
                <span>Patch Proposal</span>
                {patchDiff && <span className="text-[10px] text-emerald-400 font-mono">Unified Diff</span>}
              </div>
              <pre className="flex-1 overflow-auto rounded-lg border border-slate-800 bg-black/20 p-3 text-[11px] text-slate-300 font-mono">
                {patchDiff || "No patch event received yet."}
              </pre>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
