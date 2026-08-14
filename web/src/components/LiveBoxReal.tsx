"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

interface LiveBoxProps {
  isOpen: boolean;
  onClose: () => void;
  issue: string;
  model: string;
  repoPath: string;
  mockMode: boolean;
  onRunComplete: (runId: string, success: boolean) => void;
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

export function LiveBoxReal({ isOpen, onClose, issue, model, repoPath, mockMode, onRunComplete }: LiveBoxProps) {
  const [steps, setSteps] = useState<StepState[]>(initialSteps);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [patchDiff, setPatchDiff] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("idle");
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => () => eventSourceRef.current?.close(), []);

  const addLog = useCallback((entry: LogEntry) => {
    setLogs(prev => [...prev, entry]);
  }, []);

  const sendControl = useCallback(async (action: string) => {
    if (!runId) return;
    const response = await fetch("/api/v1/run/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId, action }),
    });
    if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || `Control action failed: ${action}`);
  }, [runId]);

  const startStream = useCallback((id: string) => {
    eventSourceRef.current?.close();
    const source = new EventSource(`/api/v1/stream/${encodeURIComponent(id)}`);
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

    try {
      const response = await fetch("/api/v1/run", {
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

  const completed = useMemo(() => steps.filter(step => step.status === "completed").length, [steps]);
  const progress = Math.round((completed / steps.length) * 100);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4" role="dialog" aria-modal="true" aria-labelledby="livebox-title">
      <div className="flex h-[88vh] w-[94vw] max-w-6xl flex-col overflow-hidden rounded-2xl border border-slate-800 bg-[#090D16] shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <div>
            <h2 id="livebox-title" className="text-sm font-semibold text-white">Live Pipeline Execution</h2>
            <p className="mt-1 text-xs text-slate-400">Backend-driven events only — no client-side execution simulation.</p>
          </div>
          <button onClick={onClose} className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800">Close</button>
        </div>

        <div className="grid flex-1 min-h-0 grid-cols-1 gap-4 p-5 lg:grid-cols-3">
          <section className="min-h-0 rounded-xl border border-slate-800 bg-slate-950/40 p-4 lg:col-span-1">
            <div className="mb-4 flex items-center justify-between">
              <span className="text-xs font-medium text-slate-300">Run</span>
              <span className="text-xs text-slate-500">{runId || "not started"}</span>
            </div>
            <div className="mb-4 rounded-lg border border-slate-800 p-3 text-xs text-slate-300">{issue || "No issue provided"}</div>
            <div className="mb-4 h-2 overflow-hidden rounded bg-slate-800"><div className="h-full bg-indigo-500 transition-all" style={{ width: `${progress}%` }} /></div>
            <div className="mb-4 text-xs text-slate-400">Status: <span className="text-slate-200">{status}</span></div>
            <div className="space-y-2">
              {steps.map(step => (
                <div key={step.name} className="flex items-center justify-between rounded-lg border border-slate-800 px-3 py-2 text-xs">
                  <span className="text-slate-300">{step.name}</span>
                  <span className="text-slate-500">{step.status}</span>
                </div>
              ))}
            </div>
            <div className="mt-5 grid grid-cols-2 gap-2">
              {!isRunning ? (
                <button onClick={handleStart} disabled={!issue.trim()} className="rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-40">Start real run</button>
              ) : (
                <button onClick={() => handleAction("cancel")} className="rounded-lg bg-rose-600 px-3 py-2 text-xs font-medium text-white">Cancel</button>
              )}
              <button onClick={() => handleAction("pause")} disabled={!runId || !isRunning} className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 disabled:opacity-40">Pause</button>
              <button onClick={() => handleAction("resume")} disabled={!runId} className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 disabled:opacity-40">Resume</button>
              <button onClick={() => handleAction("step")} disabled={!runId} className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 disabled:opacity-40">Step</button>
            </div>
            {mockMode && <p className="mt-3 rounded-lg border border-amber-900/60 bg-amber-950/30 p-2 text-[11px] text-amber-300">Mock mode was explicitly enabled. Production runtime guards reject mock execution.</p>}
            {error && <p role="alert" className="mt-3 rounded-lg border border-rose-900/60 bg-rose-950/30 p-2 text-[11px] text-rose-300">{error}</p>}
          </section>

          <section className="min-h-0 rounded-xl border border-slate-800 bg-slate-950/40 p-4 lg:col-span-2">
            <div className="mb-3 text-xs font-medium text-slate-300">Live event stream</div>
            <div className="h-[42%] overflow-auto rounded-lg border border-slate-800 bg-black/20 p-3 font-mono text-[11px]">
              {logs.length === 0 ? <div className="text-slate-600">Waiting for backend events…</div> : logs.map((log, index) => (
                <div key={`${log.timestamp}-${index}`} className="mb-2"><span className="text-slate-600">{log.timestamp}</span> <span className="text-indigo-300">[{log.agent}]</span> <span className="text-slate-400">[{log.level}]</span> {log.message}</div>
              ))}
            </div>
            <div className="mt-4 text-xs font-medium text-slate-300">Patch proposal</div>
            <pre className="mt-2 h-[45%] overflow-auto rounded-lg border border-slate-800 bg-black/20 p-3 text-[11px] text-slate-300">{patchDiff || "No patch event received yet."}</pre>
          </section>
        </div>
      </div>
    </div>
  );
}
