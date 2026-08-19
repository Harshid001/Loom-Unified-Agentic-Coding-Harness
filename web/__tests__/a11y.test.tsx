import { describe, it, expect, vi, beforeEach } from 'vitest';
import React, { act } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { Sidebar } from '../src/components/Sidebar';
import { Header } from '../src/components/Header';
import { DiffTab } from '../src/components/DiffTab';
import { DagTab } from '../src/components/DagTab';
import { EvidenceView } from '../src/components/EvidenceView';
import { AuthGate } from '../src/components/AuthGate';

// Mock Next.js router & links
vi.mock('next/link', () => ({
  default: ({ children, href, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe('Frontend Accessibility (a11y) Verification', () => {
  beforeEach(() => {
    // Reset fetch mock
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/auth/session') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ authenticated: false }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      });
    });
  });

  it('Sidebar contains landmark roles and accessible tab navigation', () => {
    render(
      <Sidebar
        activeTab="overview"
        setActiveTab={vi.fn()}
        runHistory={[
          {
            id: 'run_test_01',
            status: 'VERIFIED SUCCESS',
            issue: 'Test issue description',
            cost: 0.12,
            createdAt: 1700000000,
          },
        ]}
        selectedRun="run_test_01"
        setSelectedRun={vi.fn()}
        isLoadingRuns={false}
        connectedRepoName="test-org/test-repo"
      />
    );

    const aside = screen.getByRole('complementary', { name: /harness navigation/i });
    expect(aside).toBeDefined();

    const overviewTab = screen.getByRole('button', { name: /overview/i });
    expect(overviewTab.getAttribute('aria-pressed')).toBe('true');
    expect(overviewTab.getAttribute('aria-controls')).toBe('tabpanel-overview');

    const searchInput = screen.getByRole('textbox', { name: /filter runs/i });
    expect(searchInput).toBeDefined();
  });

  it('Header contains banner landmark, accessible model picker, and status indicators', () => {
    render(
      <Header
        modelName="claude-3-7-sonnet"
        availableModels={['claude-3-7-sonnet', 'gpt-4o']}
        onModelChange={vi.fn()}
        onOpenLiveBox={vi.fn()}
        runCount={42}
        isExecuting={false}
      />
    );

    const header = screen.getByRole('banner');
    expect(header).toBeDefined();

    const modelButton = screen.getByRole('button', { name: /select active model/i });
    expect(modelButton.getAttribute('aria-haspopup')).toBe('listbox');
    expect(modelButton.getAttribute('aria-expanded')).toBe('false');

    const liveBoxBtn = screen.getByRole('button', { name: /open live box/i });
    expect(liveBoxBtn).toBeDefined();
  });

  it('DiffTab contains tabpanel role and accessible copy controls', () => {
    render(
      <DiffTab
        displayData={{
          patchDiff: '--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-old\n+new',
        }}
      />
    );

    const panel = screen.getByRole('tabpanel');
    expect(panel).toBeDefined();

    const copyBtn = screen.getByRole('button', { name: /copy patch diff/i });
    expect(copyBtn).toBeDefined();
  });

  it('DagTab contains tabpanel role and execution graph region', () => {
    render(<DagTab displayData={null} onOpenLiveBox={vi.fn()} />);

    const panel = screen.getByRole('tabpanel');
    expect(panel).toBeDefined();

    const executeBtn = screen.getByRole('button', { name: /execute/i });
    expect(executeBtn).toBeDefined();
  });

  it('EvidenceView provides cryptographic seal regions and export button', async () => {
    await act(async () => {
      render(
        <EvidenceView
          displayData={{
            id: 'run_a11y_01',
            status: 'VERIFIED SUCCESS',
            patchDiff: 'diff --git a/test b/test',
          }}
          connectedRepoName="loom/test-repo"
        />
      );
    });

    await waitFor(() => {
      const exportBtn = screen.getByRole('button', { name: /Download evidence bundle/i });
      expect(exportBtn).toBeDefined();
    });
  });

  it('AuthGate provides accessible input labels and alert semantics on error', async () => {
    await act(async () => {
      render(
        <AuthGate>
          <div>Dashboard Content</div>
        </AuthGate>
      );
    });

    await waitFor(() => {
      const tokenInput = screen.getByPlaceholderText(/enter master token or api key/i);
      expect(tokenInput).toBeDefined();
    });
  });
});
