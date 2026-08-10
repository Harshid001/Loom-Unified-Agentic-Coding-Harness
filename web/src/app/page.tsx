"use client";

import React, { useState } from 'react';
import { useRuns } from '../hooks/useRuns';
import { Header } from '../components/Header';
import { Sidebar } from '../components/Sidebar';
import { OverviewTab } from '../components/OverviewTab';
import { DagTab } from '../components/DagTab';
import { DiffTab } from '../components/DiffTab';
import { AblationsTab } from '../components/AblationsTab';
import { NewRunModal } from '../components/NewRunModal';

export default function LoomDashboard() {
  const [activeTab, setActiveTab] = useState<'overview' | 'dag' | 'diff' | 'ablations'>('overview');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newIssue, setNewIssue] = useState('');
  const [isExecuting, setIsExecuting] = useState(false);

  const {
    selectedRun,
    setSelectedRun,
    runHistory,
    selectedRunDetails,
    isLoadingRuns,
    errorBanner,
    setErrorBanner,
    fetchRuns
  } = useRuns();

  const handleStartRun = async () => {
    if (!newIssue.trim()) return;
    setIsExecuting(true);
    setErrorBanner(null);
    try {
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ issue: newIssue, mock: false })
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: 'Server error' }));
        throw new Error(errorData.detail || `Request failed with code ${res.status}`);
      }

      const data = await res.json();
      setSelectedRun(data.run_id);
      fetchRuns();
      setNewIssue('');
      setIsModalOpen(false);
      setActiveTab('overview');
    } catch (e: any) {
      setErrorBanner(`Run creation failed: ${e.message}`);
    } finally {
      setIsExecuting(false);
    }
  };

  const handleRollback = async () => {
    if (!selectedRun) return;
    try {
      const res = await fetch(`/api/rollback/${selectedRun}`, { method: 'POST' });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: 'Rollback failed' }));
        throw new Error(errData.detail || 'Rollback execution failed');
      }
      setErrorBanner(null);
      // PRD-009: In-app UI notification instead of native alert
      const banner = document.getElementById('notice-banner');
      if (banner) {
        banner.textContent = `Rollback successful for run ${selectedRun}`;
        banner.style.display = 'block';
        setTimeout(() => { banner.style.display = 'none'; }, 5000);
      }
    } catch (err: any) {
      setErrorBanner(`Rollback failed: ${err.message}`);
    }
  };

  const checkpoint = selectedRunDetails?.checkpoint;
  const traceEvents = selectedRunDetails?.trace_events || [];

  const displayData = checkpoint ? {
    id: checkpoint.run_id,
    issue: checkpoint.issue_description || 'No issue description available',
    status: checkpoint.verification_passed ? 'VERIFIED SUCCESS' : 'EXECUTED',
    duration: checkpoint.duration_seconds ? `${checkpoint.duration_seconds.toFixed(1)}s` : '--',
    cost: checkpoint.shared_data?.cost_report?.total_cost_usd ? `$${checkpoint.shared_data.cost_report.total_cost_usd.toFixed(4)}` : '--',
    model: checkpoint.shared_data?.model || 'gpt-4o',
    nodes: traceEvents.length > 0 ? traceEvents.map((t: any) => ({
      name: t.node_name || 'step',
      label: t.event_type || 'Agent Execution',
      status: t.status || 'completed',
      duration: t.duration ? `${t.duration}s` : '--',
      cost: t.cost ? `$${t.cost.toFixed(4)}` : '--'
    })) : [
      { name: 'onboarding', label: 'Repo Mapper', status: 'pending', duration: '--', cost: '--' },
      { name: 'reproduction', label: 'Reproduction Agent', status: 'pending', duration: '--', cost: '--' },
      { name: 'patcher', label: 'Patcher Agent', status: 'pending', duration: '--', cost: '--' },
      { name: 'verifier', label: 'Verification Runner', status: 'pending', duration: '--', cost: '--' },
      { name: 'reviewer', label: 'Evidence Bundle Reviewer', status: 'pending', duration: '--', cost: '--' },
    ],
    patchDiff: checkpoint.patch_diff || 'No patch diff recorded for this run.',
    reproductionTest: checkpoint.reproduction_test
  } : null;

  return (
    <div className="min-h-screen bg-[#0B0F19] text-gray-100 flex flex-col font-sans">
      <Header 
        modelName={displayData?.model} 
        onOpenModal={() => setIsModalOpen(true)} 
      />

      {errorBanner && (
        <div className="bg-amber-500/10 border-b border-amber-500/30 px-6 py-2 text-xs text-amber-400 font-mono flex items-center justify-between" role="alert">
          <span>⚠️ {errorBanner}</span>
          <button onClick={() => setErrorBanner(null)} className="text-amber-500 hover:text-amber-300" aria-label="Dismiss error notification">✕</button>
        </div>
      )}

      <main className="flex-1 flex max-w-7xl w-full mx-auto p-6 gap-6">
        <Sidebar
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          runHistory={runHistory}
          selectedRun={selectedRun}
          setSelectedRun={setSelectedRun}
          isLoadingRuns={isLoadingRuns}
        />

        <section className="flex-1 flex flex-col">
          {activeTab === 'overview' && (
            <OverviewTab
              displayData={displayData}
              selectedRun={selectedRun}
              onRollback={handleRollback}
            />
          )}
          {activeTab === 'dag' && <DagTab displayData={displayData} />}
          {activeTab === 'diff' && <DiffTab displayData={displayData} />}
          {activeTab === 'ablations' && <AblationsTab displayData={displayData} />}
        </section>
      </main>

      <NewRunModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        newIssue={newIssue}
        setNewIssue={setNewIssue}
        isExecuting={isExecuting}
        onSubmit={handleStartRun}
      />
    </div>
  );
}
