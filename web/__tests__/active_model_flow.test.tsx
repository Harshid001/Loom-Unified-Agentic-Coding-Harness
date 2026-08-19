import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DagTab } from '../src/components/DagTab';
import { OverviewTab } from '../src/components/OverviewTab';
import { NewRunModal } from '../src/components/NewRunModal';
import { LiveBoxReal } from '../src/components/LiveBoxReal';

describe('Active Model Propagation & Display across Components', () => {
  it('DagTab displays the configured activeModel on repro/patcher stages', () => {
    render(<DagTab displayData={null} activeModel="gemini-2.5-pro" />);
    expect(screen.getByText(/5-Stage Autonomous Execution Graph/i)).toBeInTheDocument();
    expect(screen.getByText('MAPPER')).toBeInTheDocument();
    expect(screen.getByText('REPRO')).toBeInTheDocument();
    expect(screen.getByText('PATCH')).toBeInTheDocument();

    // Click on REPRO stage to inspect detail card
    fireEvent.click(screen.getByText('REPRO'));
    expect(screen.getByText('gemini-2.5-pro')).toBeInTheDocument();
  });

  it('OverviewTab displays the ACTIVE MODEL card in repository state strip', () => {
    render(
      <OverviewTab
        displayData={null}
        selectedRun={null}
        onRollback={vi.fn()}
        isLoadingDetails={false}
        activeModel="deepseek-v3"
        connectedRepo={{ fullName: 'test/repo', name: 'repo', owner: 'test', defaultBranch: 'main', selectedBranch: 'main', htmlUrl: 'https://github.com/test/repo', isPrivate: false }}
      />
    );

    expect(screen.getByText(/ACTIVE MODEL/i)).toBeInTheDocument();
    expect(screen.getByText('deepseek-v3')).toBeInTheDocument();
  });

  it('NewRunModal displays the active model pill alongside repo and branch', () => {
    render(
      <NewRunModal
        isOpen={true}
        onClose={vi.fn()}
        newIssue="Fix bug in auth"
        setNewIssue={vi.fn()}
        isExecuting={false}
        onSubmit={vi.fn()}
        repoName="owner/awesome-project"
        branchName="feature-branch"
        activeModel="claude-3-7-sonnet-20250219"
      />
    );

    expect(screen.getByText('owner/awesome-project')).toBeInTheDocument();
    expect(screen.getByText('feature-branch')).toBeInTheDocument();
    expect(screen.getByText('claude-3-7-sonnet-20250219')).toBeInTheDocument();
  });

  it('LiveBoxReal displays active model and per-step assigned models', () => {
    render(
      <LiveBoxReal
        isOpen={true}
        onClose={vi.fn()}
        issue="Test issue description"
        model="gpt-4o"
        repoPath="owner/repo"
        mockMode={true}
        onRunComplete={vi.fn()}
        availableModels={['gpt-4o', 'gemini-2.5-pro', 'claude-3-7-sonnet-20250219']}
        onModelChange={vi.fn()}
      />
    );

    expect(screen.getByText(/Live Pipeline Execution/i)).toBeInTheDocument();
    expect(screen.getAllByText('gpt-4o').length).toBeGreaterThan(0);
    expect(screen.getByText('Tree-Sitter AST')).toBeInTheDocument();
    expect(screen.getAllByText('Tier B Container').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Source Mapper')).toBeInTheDocument();
    expect(screen.getAllByText('Proof Layer Auditor').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Security Linter')).toBeInTheDocument();
    expect(screen.getByText('Quality Gate')).toBeInTheDocument();
  });
});
