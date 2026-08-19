import { useState, useEffect, useCallback, useRef } from 'react';

export interface RunItem {
  id: string;
  issue: string;
  status: string;
  cost?: number;
  createdAt?: number;
  duration?: number;
}

interface RunDetails {
  checkpoint: any;
  trace_events: any[];
}

export function useRuns() {
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [runHistory, setRunHistory] = useState<RunItem[]>([]);
  const [selectedRunDetails, setSelectedRunDetails] = useState<RunDetails | null>(null);
  const [isLoadingRuns, setIsLoadingRuns] = useState<boolean>(true);
  const [isLoadingDetails, setIsLoadingDetails] = useState<boolean>(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchRuns = useCallback(() => {
    fetch('/api/runs')
      .then(res => {
        if (!res.ok) throw new Error(`API returned status ${res.status}`);
        return res.json();
      })
      .then(data => {
        if (Array.isArray(data)) {
          const mappedRuns: RunItem[] = data.map((r: any) => ({
            id: r.id,
            issue: r.issue,
            status: r.status,
            cost: r.cost,
            createdAt: r.created_at,
          }));
          setRunHistory(mappedRuns);
          if (mappedRuns.length > 0 && !selectedRun) {
            setSelectedRun(mappedRuns[0].id);
          }
          setErrorBanner(null);
        }
      })
      .catch(err => {
        setErrorBanner(`Backend connection warning: ${err.message}.`);
      })
      .finally(() => {
        setIsLoadingRuns(false);
      });
  }, [selectedRun]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  useEffect(() => {
    pollRef.current = setInterval(fetchRuns, 15000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchRuns]);

  useEffect(() => {
    if (!selectedRun) {
      setSelectedRunDetails(null);
      return;
    }
    setIsLoadingDetails(true);
    fetch(`/api/runs/${selectedRun}`)
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data && data.checkpoint) {
          setSelectedRunDetails(data);
        } else {
          setSelectedRunDetails(null);
        }
      })
      .catch((err) => {
        setErrorBanner(`Failed to load details for ${selectedRun}: ${err.message}`);
        setSelectedRunDetails(null);
      })
      .finally(() => {
        setIsLoadingDetails(false);
      });
  }, [selectedRun]);

  return {
    selectedRun,
    setSelectedRun,
    runHistory,
    selectedRunDetails,
    isLoadingRuns,
    isLoadingDetails,
    errorBanner,
    setErrorBanner,
    fetchRuns
  };
}