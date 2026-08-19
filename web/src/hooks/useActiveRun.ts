import { useState, useEffect, useCallback, useRef } from 'react';

export interface ActiveRunState {
  activeRunId: string | null;
  currentStage: string;
  currentStageIndex: number;
  totalStages: number;
  logLines: LogLine[];
  elapsedSeconds: number;
  isActive: boolean;
}

export interface LogLine {
  timestamp: string;
  level: string;
  agent: string;
  message: string;
}

const STAGE_ORDER = ['onboarding', 'reproduction', 'patcher', 'verifier', 'reviewer'];
const STAGE_LABELS: Record<string, string> = {
  onboarding: 'MAPPER',
  reproduction: 'REPRO',
  patcher: 'PATCH',
  verifier: 'VERIFY',
  reviewer: 'REVIEW',
};

export function useActiveRun() {
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [currentStage, setCurrentStage] = useState<string>('');
  const [currentStageIndex, setCurrentStageIndex] = useState<number>(0);
  const [logLines, setLogLines] = useState<LogLine[]>([]);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);
  const [isActive, setIsActive] = useState(false);

  const eventSourceRef = useRef<EventSource | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number | null>(null);

  // Poll for active runs
  const checkForActiveRun = useCallback(() => {
    fetch('/api/runs')
      .then(res => res.ok ? res.json() : [])
      .then(data => {
        if (!Array.isArray(data)) return;
        const active = data.find((r: any) =>
          r.status !== 'VERIFIED SUCCESS' &&
          r.status !== 'FAILED' &&
          r.status !== 'COMPLETED'
        );
        if (active) {
          setActiveRunId(active.id);
          setIsActive(true);
        } else {
          if (isActive) {
            // Run just completed
            setIsActive(false);
            setActiveRunId(null);
            setCurrentStage('');
            setCurrentStageIndex(0);
          }
        }
      })
      .catch(() => {});
  }, [isActive]);

  // Poll every 3 seconds
  useEffect(() => {
    checkForActiveRun();
    pollRef.current = setInterval(checkForActiveRun, 3000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [checkForActiveRun]);

  // SSE connection for log streaming
  useEffect(() => {
    if (!activeRunId || !isActive) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      return;
    }

    // Start elapsed timer
    startTimeRef.current = Date.now();
    timerRef.current = setInterval(() => {
      if (startTimeRef.current) {
        setElapsedSeconds(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }
    }, 1000);

    // Try to connect to SSE stream
    try {
      const es = new EventSource(`/api/stream/${encodeURIComponent(activeRunId)}`);
      eventSourceRef.current = es;

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          // Track stage transitions
          if (data.node_name || data.agent || data.step) {
            const stageName = data.node_name || data.agent || data.step;
            const stageIdx = STAGE_ORDER.indexOf(stageName);
            if (stageIdx >= 0) {
              setCurrentStage(STAGE_LABELS[stageName] || stageName);
              setCurrentStageIndex(stageIdx + 1);
            }
          }

          // Add log line (keep last 50)
          const logLine: LogLine = {
            timestamp: data.timestamp || new Date().toISOString(),
            level: data.level || data.log_level || 'info',
            agent: data.agent || data.node_name || 'system',
            message: data.message || data.text || data.log || JSON.stringify(data),
          };

          setLogLines(prev => {
            const updated = [...prev, logLine];
            return updated.slice(-50);
          });

          // Check if run is done
          if (data.status === 'completed' || data.status === 'failed' || data.event_type === 'run_complete') {
            setIsActive(false);
          }
        } catch {
          // Ignore parse errors
        }
      };

      es.onerror = () => {
        // SSE connection failed — that's ok, we still have polling
        es.close();
        eventSourceRef.current = null;
      };
    } catch {
      // SSE not available
    }

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [activeRunId, isActive]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (timerRef.current) clearInterval(timerRef.current);
      if (eventSourceRef.current) eventSourceRef.current.close();
    };
  }, []);

  const formatElapsed = useCallback((secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }, []);

  return {
    activeRunId,
    currentStage,
    currentStageIndex,
    totalStages: STAGE_ORDER.length,
    logLines,
    elapsedSeconds,
    elapsedFormatted: formatElapsed(elapsedSeconds),
    isActive,
  } satisfies ActiveRunState & { elapsedFormatted: string };
}
