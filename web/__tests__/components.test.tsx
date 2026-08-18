import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { screen, fireEvent } from '@testing-library/dom';
import { DiffTab } from '../src/components/DiffTab';
import { DagTab } from '../src/components/DagTab';
import { AblationsTab } from '../src/components/AblationsTab';
import { EvidenceView } from '../src/components/EvidenceView';
import { Header } from '../src/components/Header';

describe('DiffTab component', () => {
  it('renders placeholder when no displayData is provided', () => {
    render(<DiffTab displayData={null} />);
    expect(screen.getByText(/No Verified Patch Selected/i)).toBeInTheDocument();
  });

  it('renders syntax-highlighted unified diff lines', () => {
    const mockData = {
      patchDiff: `--- a/src/app.py\n+++ b/src/app.py\n@@ -1,3 +1,4 @@\n-old line\n+new line\n unchanged`,
    };

    render(<DiffTab displayData={mockData} />);
    expect(screen.getByText(/Verified Unified Patch Diff/i)).toBeInTheDocument();
    expect(screen.getByText('VALIDATED')).toBeInTheDocument();
    expect(screen.getByText(/-old line/i)).toBeInTheDocument();
    expect(screen.getByText(/\+new line/i)).toBeInTheDocument();
  });
});

describe('DagTab component', () => {
  it('renders topology when no displayData is provided', () => {
    render(<DagTab displayData={null} />);
    expect(screen.getByText(/5-Stage Autonomous Execution Graph/i)).toBeInTheDocument();
    expect(screen.getByText('MAPPER')).toBeInTheDocument();
  });

  it('renders all 5 pipeline DAG nodes with progress', () => {
    const mockData = {
      nodes: [
        { status: 'completed', duration: '1.2s', cost: '$0.001' },
        { status: 'completed', duration: '2.0s', cost: '$0.002' },
        { status: 'running', duration: '0.5s', cost: '$0.0005' },
        { status: 'pending' },
        { status: 'pending' },
      ],
    };

    render(<DagTab displayData={mockData} />);
    expect(screen.getByText(/5-Stage Autonomous Execution Graph/i)).toBeInTheDocument();
    expect(screen.getByText('MAPPER')).toBeInTheDocument();
    expect(screen.getByText('REPRO')).toBeInTheDocument();
    expect(screen.getByText('PATCH')).toBeInTheDocument();
    expect(screen.getByText('VERIFY')).toBeInTheDocument();
    expect(screen.getByText('REVIEW')).toBeInTheDocument();
  });
});

describe('EvidenceView component', () => {
  it('renders standby state when no run is active', () => {
    render(<EvidenceView displayData={null} runId={undefined} connectedRepoName="Harshid001/Loom-Harness" />);
    expect(screen.getByText(/No Execution Evidence Generated Yet/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Harshid001\/Loom-Harness/i).length).toBeGreaterThan(0);
  });

  it('renders cryptographic proof layer and SHA-256 artifacts for active run', async () => {
    const mockDisplay = {
      id: 'run_101',
      status: 'VERIFIED SUCCESS',
      patchDiff: '+ surgical fix',
      reproductionTest: 'def test_repro(): pass',
      snapshotId: 'snap_101',
    };
    render(<EvidenceView displayData={mockDisplay} runId="run_101" integrityValid={true} />);
    expect(screen.getByText(/SHA-256 Hash Chain Audit Bundle/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/INTEGRITY VALID/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Verification Proof Checklist/i)).toBeInTheDocument();
    expect(screen.getByText(/Chained Artifact Manifest/i)).toBeInTheDocument();
  });
});

describe('AblationsTab component', () => {
  it('renders standard ablation benchmark matrix when no custom data is provided', () => {
    render(<AblationsTab displayData={null} />);
    expect(screen.getByText(/Ablation Experiment Framework/i)).toBeInTheDocument();
    expect(screen.getByText(/Full Loom Harness/i)).toBeInTheDocument();
    expect(screen.getByText(/CALIBRATION PENDING/i)).toBeInTheDocument();
  });

  it('renders custom ablation data if supplied', () => {
    const customData = {
      ablations: [
        { name: 'Custom Harness Tier', memory: true, context: true, multiAgent: true, passRate: '98.5%', cost: '$0.0020' },
      ],
    };

    render(<AblationsTab displayData={customData} />);
    expect(screen.getByText(/Custom Harness Tier/i)).toBeInTheDocument();
    expect(screen.getByText(/98.5%/i)).toBeInTheDocument();
  });
});

describe('Header component', () => {
  it('renders brand, active model, and responsive logout button', () => {
    render(
      <Header
        modelName="claude-3-7-sonnet"
        availableModels={['claude-3-7-sonnet', 'gpt-4o']}
        onModelChange={vi.fn()}
        onOpenLiveBox={vi.fn()}
        runCount={5}
      />
    );

    expect(screen.getByText('LOOM')).toBeInTheDocument();
    expect(screen.getByText('claude-3-7-sonnet')).toBeInTheDocument();
    expect(screen.getByText('Logout')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Log out of Loom Dashboard/i })).toBeInTheDocument();
  });
});

describe('AuthGate component', () => {
  it('renders Google sign in button and token login form', async () => {
    const { AuthGate } = await import('../src/components/AuthGate');
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ authenticated: false }),
    });

    render(
      <AuthGate>
        <div>Protected Content</div>
      </AuthGate>
    );

    const { waitFor } = await import('@testing-library/react');
    await waitFor(() => {
      expect(screen.getByText(/Sign in with Google/i)).toBeInTheDocument();
      expect(screen.getByText(/or continue with token/i)).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/Enter master token or API key/i)).toBeInTheDocument();
      expect(screen.getByText(/Sign in with Token/i)).toBeInTheDocument();
    });
  });
});
