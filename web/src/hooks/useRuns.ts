import { useState, useEffect, useCallback } from 'react';

export interface RunItem {
  id: string;
  issue: string;
  status: string;
  cost?: number;
}

export function useRuns() {
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [runHistory, setRunHistory] = useState<RunItem[]>([]);
  const [selectedRunDetails, setSelectedRunDetails] = useState<any>(null);
  const [isLoadingRuns, setIsLoadingRuns] = useState<boolean>(true);
  const [isLoadingDetails, setIsLoadingDetails] = useState<boolean>(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);

  const fetchRuns = useCallback(() => {
    setIsLoadingRuns(true);
    fetch('/api/runs')
      .then(res => {
        if (!res.ok) throw new Error(`API returned status ${res.status}`);
        return res.json();
      })
      .then(data => {
        if (Array.isArray(data)) {
          const mappedRuns = data.map((r: any) => ({
            id: r.id,
            issue: r.issue,
            status: r.status,
            cost: r.cost
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
