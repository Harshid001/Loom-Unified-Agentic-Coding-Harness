import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { screen, fireEvent } from '@testing-library/dom';
import { RepoConnectModal } from '../src/components/RepoConnectModal';
import { GitHubIssuesDrawer } from '../src/components/GitHubIssuesDrawer';
import { Header } from '../src/components/Header';
import { POPULAR_STARTER_REPOS } from '../src/hooks/useGitHub';

describe('RepoConnectModal component', () => {
  const mockGithubState: any = {
    token: null,
    user: null,
    userRepos: [],
    connectedRepo: {
      fullName: 'Harshid001/Loom-Unified-Agentic-Coding-Harness',
      name: 'Loom-Unified-Agentic-Coding-Harness',
      owner: 'Harshid001',
      defaultBranch: 'main',
      selectedBranch: 'main',
      htmlUrl: 'https://github.com/Harshid001/Loom-Unified-Agentic-Coding-Harness',
      isPrivate: false,
    },
    repoIssues: [],
    repoBranches: [{ name: 'main' }],
    isLoadingUser: false,
    isLoadingRepos: false,
    isLoadingIssues: false,
    isLoadingBranches: false,
    error: null,
    authenticate: vi.fn(),
    disconnect: vi.fn(),
    loadUserRepos: vi.fn(),
    loadBranches: vi.fn(),
    loadIssues: vi.fn(),
    connectRepository: vi.fn(),
    setSelectedBranch: vi.fn(),
    createPullRequest: vi.fn(),
  };

  it('renders modal with connection tabs and active repo banner', () => {
    const handleClose = vi.fn();
    render(
      <RepoConnectModal
        isOpen={true}
        onClose={handleClose}
        githubState={mockGithubState}
      />
    );

    expect(screen.getByText(/Connect GitHub & Repositories/i)).toBeInTheDocument();
    expect(screen.getByTestId('tab-account')).toBeInTheDocument();
    expect(screen.getByTestId('tab-url')).toBeInTheDocument();
    expect(screen.getByTestId('tab-starters')).toBeInTheDocument();
    expect(screen.getByTestId('tab-local')).toBeInTheDocument();
    expect(screen.getByText(/Harshid001\/Loom-Unified-Agentic-Coding-Harness/i)).toBeInTheDocument();
  });

  it('switches to Curated Starter Repos tab and connects a starter repo', () => {
    const handleClose = vi.fn();
    render(
      <RepoConnectModal
        isOpen={true}
        onClose={handleClose}
        githubState={mockGithubState}
      />
    );

    const startersTab = screen.getByTestId('tab-starters');
    fireEvent.click(startersTab);

    expect(screen.getByText(/fastapi\/fastapi/i)).toBeInTheDocument();
    expect(screen.getByText(/vercel\/next.js/i)).toBeInTheDocument();

    const connectButtons = screen.getAllByRole('button', { name: /Connect/i });
    expect(connectButtons.length).toBeGreaterThan(0);
    fireEvent.click(connectButtons[0]);

    expect(mockGithubState.connectRepository).toHaveBeenCalled();
  });

  it('switches to Direct GitHub URL tab and inspects repository', () => {
    const handleClose = vi.fn();
    render(
      <RepoConnectModal
        isOpen={true}
        onClose={handleClose}
        githubState={mockGithubState}
      />
    );

    const directUrlTab = screen.getByTestId('tab-url');
    fireEvent.click(directUrlTab);

    const input = screen.getByPlaceholderText(/https:\/\/github.com\/owner\/repo/i);
    expect(input).toBeInTheDocument();
    fireEvent.change(input, { target: { value: 'facebook/react' } });

    const inspectBtn = screen.getByRole('button', { name: /Inspect Repo/i });
    expect(inspectBtn).toBeInTheDocument();
  });

  it('switches to Local Workspace tab and sets sandbox tier', () => {
    const handleClose = vi.fn();
    render(
      <RepoConnectModal
        isOpen={true}
        onClose={handleClose}
        githubState={mockGithubState}
      />
    );

    const localTab = screen.getByTestId('tab-local');
    fireEvent.click(localTab);

    expect(screen.getByText(/Tier A: Git Worktree/i)).toBeInTheDocument();
    expect(screen.getByText(/Tier B: MicroVM/i)).toBeInTheDocument();

    const connectLocalBtn = screen.getByRole('button', { name: /Connect Local Repository/i });
    fireEvent.click(connectLocalBtn);

    expect(mockGithubState.connectRepository).toHaveBeenCalled();
    expect(handleClose).toHaveBeenCalled();
  });
});

describe('GitHubIssuesDrawer component', () => {
  const mockIssues = [
    {
      id: 1,
      number: 42,
      title: 'Fix race condition in state machine DAG',
      body: 'Preconditions check can trigger concurrent transitions.',
      state: 'open' as const,
      html_url: 'https://github.com/owner/repo/issues/42',
      user: { login: 'agent-dev', avatar_url: '' },
      labels: [{ id: 10, name: 'bug', color: 'd73a4a' }],
      comments: 2,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    {
      id: 2,
      number: 55,
      title: 'Add support for DeepSeek R1 models',
      body: 'Integrate LiteLLM routing for reasoning models.',
      state: 'open' as const,
      html_url: 'https://github.com/owner/repo/issues/55',
      user: { login: 'ai-eng', avatar_url: '' },
      labels: [{ id: 11, name: 'enhancement', color: 'a2eeef' }],
      comments: 5,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ];

  it('renders list of open issues with labels and comments count', () => {
    const handleClose = vi.fn();
    const handleRefresh = vi.fn();
    const handleSelectIssue = vi.fn();

    render(
      <GitHubIssuesDrawer
        isOpen={true}
        onClose={handleClose}
        connectedRepo={{
          fullName: 'owner/repo',
          name: 'repo',
          owner: 'owner',
          defaultBranch: 'main',
          selectedBranch: 'main',
          htmlUrl: 'https://github.com/owner/repo',
          isPrivate: false,
        }}
        issues={mockIssues}
        isLoading={false}
        onRefresh={handleRefresh}
        onSelectIssue={handleSelectIssue}
      />
    );

    expect(screen.getByText(/GitHub Issues Explorer/i)).toBeInTheDocument();
    expect(screen.getByText(/Fix race condition in state machine DAG/i)).toBeInTheDocument();
    expect(screen.getByText(/Add support for DeepSeek R1 models/i)).toBeInTheDocument();
    expect(screen.getByText(/#42/i)).toBeInTheDocument();
    expect(screen.getByText(/#55/i)).toBeInTheDocument();
  });

  it('allows searching issues and triggers Solve with Loom', () => {
    const handleClose = vi.fn();
    const handleRefresh = vi.fn();
    const handleSelectIssue = vi.fn();

    render(
      <GitHubIssuesDrawer
        isOpen={true}
        onClose={handleClose}
        connectedRepo={null}
        issues={mockIssues}
        isLoading={false}
        onRefresh={handleRefresh}
        onSelectIssue={handleSelectIssue}
      />
    );

    const searchInput = screen.getByPlaceholderText(/Search issues by title/i);
    fireEvent.change(searchInput, { target: { value: 'DeepSeek' } });

    expect(screen.queryByText(/Fix race condition/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Add support for DeepSeek R1 models/i)).toBeInTheDocument();

    const solveBtns = screen.getAllByRole('button', { name: /Solve with Loom/i });
    expect(solveBtns.length).toBe(1);
    fireEvent.click(solveBtns[0]);

    expect(handleSelectIssue).toHaveBeenCalledWith(expect.stringContaining('[GitHub Issue #55]'));
    expect(handleClose).toHaveBeenCalled();
  });
});

describe('Header component with GitHub integration', () => {
  it('renders connected repository and triggers issue drawer', () => {
    const handleOpenRepoModal = vi.fn();
    const handleOpenIssuesDrawer = vi.fn();

    render(
      <Header
        modelName="gpt-4o"
        availableModels={['gpt-4o']}
        onModelChange={vi.fn()}
        onOpenLiveBox={vi.fn()}
        onOpenRepoModal={handleOpenRepoModal}
        onOpenIssuesDrawer={handleOpenIssuesDrawer}
        connectedRepo={{
          fullName: 'Harshid001/Loom-Unified-Agentic-Coding-Harness',
          name: 'Loom-Unified-Agentic-Coding-Harness',
          owner: 'Harshid001',
          defaultBranch: 'main',
          selectedBranch: 'main',
          htmlUrl: 'https://github.com/Harshid001/Loom-Unified-Agentic-Coding-Harness',
          isPrivate: false,
        }}
        githubUser={{
          login: 'octocat',
          name: 'The Octocat',
          avatar_url: '',
          html_url: 'https://github.com/octocat',
          public_repos: 8,
        }}
        runCount={5}
      />
    );

    expect(screen.getByText(/Harshid001\/Loom-Unified-Agentic-Coding-Harness/i)).toBeInTheDocument();
    expect(screen.getByText(/Issues/i)).toBeInTheDocument();

    fireEvent.click(screen.getByText(/Issues/i));
    expect(handleOpenIssuesDrawer).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByText(/Harshid001\/Loom-Unified-Agentic-Coding-Harness/i));
    expect(handleOpenRepoModal).toHaveBeenCalledTimes(1);
  });
});
