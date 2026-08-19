import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { screen, fireEvent } from '@testing-library/dom';
import { Header } from '../src/components/Header';
import { Sidebar } from '../src/components/Sidebar';
import { NewRunModal } from '../src/components/NewRunModal';

describe('Header component', () => {
  it('renders title and model badge', () => {
    const handleOpenLiveBox = vi.fn();
    const handleModelChange = vi.fn();
    render(
      <Header
        modelName="claude-3-7-sonnet"
        availableModels={['claude-3-7-sonnet', 'gpt-4o']}
        onModelChange={handleModelChange}
        onOpenLiveBox={handleOpenLiveBox}
        runCount={3}
      />
    );

    expect(screen.getByText(/LOOM/i)).toBeInTheDocument();
    expect(screen.getByText(/claude-3-7-sonnet/i)).toBeInTheDocument();

    const startButton = screen.getByRole('button', { name: /Open Live Box/i });
    expect(startButton).toBeInTheDocument();

    fireEvent.click(startButton);
    expect(handleOpenLiveBox).toHaveBeenCalledTimes(1);
  });
});

describe('Sidebar component', () => {
  it('renders view navigation tabs with proper lifecycle groups', () => {
    const setTab = vi.fn();
    const setRun = vi.fn();
    render(
      <Sidebar
        activeTab="overview"
        setActiveTab={setTab}
        runHistory={[{ id: 'run_1', issue: 'Fix bug', status: 'VERIFIED SUCCESS' }]}
        selectedRun="run_1"
        setSelectedRun={setRun}
        isLoadingRuns={false}
      />
    );

    const overviewTab = screen.getByRole('button', { name: /Overview/i });
    expect(overviewTab).toBeInTheDocument();

    const dagTab = screen.getByRole('button', { name: /DAG Execution/i });
    expect(dagTab).toBeInTheDocument();

    fireEvent.click(dagTab);
    expect(setTab).toHaveBeenCalledWith('dag');
  });
});

describe('NewRunModal component', () => {
  it('handles user input and form submission', () => {
    const onClose = vi.fn();
    const setNewIssue = vi.fn();
    const onSubmit = vi.fn();

    render(
      <NewRunModal
        isOpen={true}
        onClose={onClose}
        newIssue="Test issue description"
        setNewIssue={setNewIssue}
        isExecuting={false}
        onSubmit={onSubmit}
      />
    );

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    const textarea = screen.getByPlaceholderText(/Describe the bug, feature, refactor, or GitHub issue/i);
    expect(textarea).toHaveValue('Test issue description');

    fireEvent.change(textarea, { target: { value: 'Updated prompt' } });
    expect(setNewIssue).toHaveBeenCalledWith('Updated prompt');

    const submitBtn = screen.getByRole('button', { name: /Launch Run →/i });
    fireEvent.click(submitBtn);
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });
});