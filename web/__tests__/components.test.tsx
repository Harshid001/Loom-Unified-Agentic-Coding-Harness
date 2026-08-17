import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { screen, fireEvent } from '@testing-library/dom';
import { DiffTab } from '../src/components/DiffTab';
import { DagTab } from '../src/components/DagTab';
import { AblationsTab } from '../src/components/AblationsTab';

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
    expect(screen.getByText(/Unified Diff Format/i)).toBeInTheDocument();
    expect(screen.getByText(/-old line/i)).toBeInTheDocument();
    expect(screen.getByText(/\+new line/i)).toBeInTheDocument();
  });
});

describe('DagTab component', () => {
  it('renders topology when no displayData is provided', () => {
    render(<DagTab displayData={null} />);
    expect(screen.getByText(/DAG Task Graph Topology/i)).toBeInTheDocument();
    expect(screen.getByText(/1\. Repo Mapper/i)).toBeInTheDocument();
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
    expect(screen.getByText(/DAG Task Graph Topology/i)).toBeInTheDocument();
    expect(screen.getByText(/1\. Repo Mapper/i)).toBeInTheDocument();
    expect(screen.getByText(/2\. Reproduction Agent/i)).toBeInTheDocument();
    expect(screen.getByText(/3\. Patcher Agent/i)).toBeInTheDocument();
    expect(screen.getByText(/4\. Verification Runner/i)).toBeInTheDocument();
    expect(screen.getByText(/5\. Evidence Reviewer/i)).toBeInTheDocument();
    expect(screen.getByText(/2\/5/i)).toBeInTheDocument();
  });

  it('allows clicking nodes to expand agent details', () => {
    const mockData = {
      nodes: [
        { status: 'completed', duration: '1.2s', cost: '$0.001' },
        { status: 'pending' },
        { status: 'pending' },
        { status: 'pending' },
        { status: 'pending' },
      ],
    };

    render(<DagTab displayData={mockData} />);
    const mapperBtn = screen.getByRole('button', { name: /1\. Repo Mapper/i });
    fireEvent.click(mapperBtn);

    expect(screen.getByText(/Agent:/i)).toBeInTheDocument();
    expect(screen.getByText(/onboarding/i)).toBeInTheDocument();
  });
});

describe('AblationsTab component', () => {
  it('renders standard ablation benchmark matrix when no custom data is provided', () => {
    render(<AblationsTab displayData={null} />);
    expect(screen.getByText(/Ablation Experiment Benchmark Matrix/i)).toBeInTheDocument();
    expect(screen.getByText(/Full Loom Harness/i)).toBeInTheDocument();
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

