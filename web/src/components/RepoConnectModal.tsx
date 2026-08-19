"use client";

import React, { useState, useMemo } from 'react';
import Image from 'next/image';
import {
  X,
  GitBranch,
  Search,
  Check,
  ExternalLink,
  Star,
  GitFork,
  Lock,
  Globe,
  FolderGit2,
  Sparkles,
  Loader2,
  Key,
  LogOut,
  RefreshCw,
  AlertCircle,
  Code2,
  ArrowRight,
} from 'lucide-react';
import { Github } from './GithubIcon';
import {
  useGitHub,
  POPULAR_STARTER_REPOS,
  GitHubRepo,
} from '../hooks/useGitHub';

interface RepoConnectModalProps {
  isOpen: boolean;
  onClose: () => void;
  githubState: ReturnType<typeof useGitHub>;
  onSelectRepo?: (repoPath: string) => void;
}

type TabType = 'account' | 'url' | 'starters' | 'local';

export const RepoConnectModal: React.FC<RepoConnectModalProps> = ({
  isOpen,
  onClose,
  githubState,
  onSelectRepo,
}) => {
  const [activeTab, setActiveTab] = useState<TabType>('account');
  const [patToken, setPatToken] = useState('');
  const [tokenInputError, setTokenInputError] = useState<string | null>(null);
  const [isAuthenticating, setIsAuthenticating] = useState(false);

  // Search & Filter in Account Repos
  const [searchQuery, setSearchQuery] = useState('');
  const [visibilityFilter, setVisibilityFilter] = useState<'all' | 'public' | 'private'>('all');

  // Direct URL Tab State
  const [directUrl, setDirectUrl] = useState('');
  const [urlBranch, setUrlBranch] = useState('');
  const [isValidatingUrl, setIsValidatingUrl] = useState(false);
  const [validatedRepoData, setValidatedRepoData] = useState<any | null>(null);
  const [urlError, setUrlError] = useState<string | null>(null);

  // Local Path Tab State
  const [localPath, setLocalPath] = useState('.');
  const [sandboxTier, setSandboxTier] = useState<'A' | 'B'>('A');

  const {
    user,
    token,
    userRepos,
    connectedRepo,
    isLoadingRepos,
    authenticate,
    disconnect,
    loadUserRepos,
    connectRepository,
  } = githubState;

  // Filter user repos
  const filteredRepos = useMemo(() => {
    return userRepos.filter(repo => {
      const matchesSearch =
        repo.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        repo.full_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (repo.description && repo.description.toLowerCase().includes(searchQuery.toLowerCase()));

      if (!matchesSearch) return false;
      if (visibilityFilter === 'public') return !repo.private;
      if (visibilityFilter === 'private') return repo.private;
      return true;
    });
  }, [userRepos, searchQuery, visibilityFilter]);

  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleConnectToken = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!patToken.trim()) {
      setTokenInputError('Please enter a GitHub Personal Access Token');
      return;
    }

    setIsAuthenticating(true);
    setTokenInputError(null);
    try {
      await authenticate(patToken.trim());
      setPatToken('');
    } catch (err: any) {
      setTokenInputError(err.message || 'Authentication failed. Please verify your token.');
    } finally {
      setIsAuthenticating(false);
    }
  };

  const handleValidateDirectUrl = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setUrlError(null);
    setValidatedRepoData(null);

    let clean = directUrl.trim();
    if (!clean) {
      setUrlError('Please enter a GitHub repository URL or slug (e.g. owner/repo)');
      return;
    }

    clean = clean.replace(/^https?:\/\/github\.com\//, '').replace(/\.git$/, '').trim();
    const parts = clean.split('/');
    if (parts.length < 2) {
      setUrlError('Invalid format. Use "owner/repo" or "https://github.com/owner/repo"');
      return;
    }

    const repoSlug = `${parts[0]}/${parts[1]}`;
    setIsValidatingUrl(true);

    try {
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;

      const res = await fetch(`/api/github?action=validate_repo&repo=${encodeURIComponent(repoSlug)}`, {
        headers,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Repository "${repoSlug}" could not be accessed`);
      }

      const data = await res.json();
      setValidatedRepoData(data);
      setUrlBranch(data.default_branch || 'main');
    } catch (err: any) {
      setUrlError(err.message || 'Failed to inspect GitHub repository');
    } finally {
      setIsValidatingUrl(false);
    }
  };

  const handleSelectDirectRepo = () => {
    if (!validatedRepoData) return;
    connectRepository({
      fullName: validatedRepoData.full_name,
      name: validatedRepoData.name,
      owner: validatedRepoData.owner?.login,
      defaultBranch: validatedRepoData.default_branch,
      selectedBranch: urlBranch || validatedRepoData.default_branch || 'main',
      htmlUrl: validatedRepoData.html_url,
      isPrivate: validatedRepoData.private,
      description: validatedRepoData.description,
      language: validatedRepoData.language,
      stars: validatedRepoData.stargazers_count,
    });
    if (onSelectRepo) onSelectRepo(validatedRepoData.full_name);
    onClose();
  };

  const handleSelectStarter = (starter: typeof POPULAR_STARTER_REPOS[0]) => {
    connectRepository({
      fullName: starter.fullName,
      name: starter.name,
      owner: starter.owner,
      defaultBranch: starter.defaultBranch,
      selectedBranch: starter.defaultBranch,
      htmlUrl: `https://github.com/${starter.fullName}`,
      isPrivate: false,
      description: starter.description,
      language: starter.language,
    });
    if (onSelectRepo) onSelectRepo(starter.fullName);
    onClose();
  };

  const handleSelectUserRepo = (repo: GitHubRepo) => {
    connectRepository({
      fullName: repo.full_name,
      name: repo.name,
      owner: repo.owner.login,
      defaultBranch: repo.default_branch,
      selectedBranch: repo.default_branch,
      htmlUrl: repo.html_url,
      isPrivate: repo.private,
      description: repo.description,
      language: repo.language,
      stars: repo.stargazers_count,
    });
    if (onSelectRepo) onSelectRepo(repo.full_name);
    onClose();
  };

  const handleConnectLocal = () => {
    const cleanPath = localPath.trim() || '.';
    connectRepository({
      fullName: cleanPath === '.' ? 'Local Workspace (.)' : cleanPath,
      name: cleanPath === '.' ? 'Workspace' : cleanPath.split(/[\\/]/).pop() || cleanPath,
      owner: 'local',
      defaultBranch: 'local',
      selectedBranch: 'local',
      htmlUrl: '',
      isPrivate: true,
      description: `Local filesystem repository mounted in Sandbox Tier ${sandboxTier}`,
      language: 'Local',
    });
    if (onSelectRepo) onSelectRepo(cleanPath);
    onClose();
  };

  return (
    <div
       className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md animate-fade-in cursor-pointer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="repo-modal-title"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-4xl bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] cursor-default"
        onClick={e => e.stopPropagation()}
      >
        {/* 1. Modal Header */}
        <div className="px-6 py-4 border-b border-[var(--border-subtle)] bg-[var(--bg-sidebar)] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-[var(--brand-soft)] border border-[var(--brand)]/30 flex items-center justify-center text-[var(--brand)] shrink-0">
              <Github className="h-4 w-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="repo-modal-title" className="text-sm font-bold text-[var(--text-primary)] uppercase font-mono tracking-tight">
                  Connect GitHub & Repositories
                </h2>
                <span className="status-pill status-pill-idle text-[10px]">
                  SOURCE CONTROL
                </span>
              </div>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">
                Target repositories, browse issues, and synthesize automated pull requests.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-[var(--text-muted)] hover:text-[var(--text-primary)] p-1.5 rounded-lg hover:bg-[var(--bg-hover)] transition"
            aria-label="Close modal"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* 2. Currently Targeting Status Strip */}
        {connectedRepo && (
          <div className="bg-[var(--bg-elevated)] border-b border-[var(--border-subtle)] px-6 py-2.5 flex items-center justify-between text-xs flex-wrap gap-2">
            <div className="flex items-center gap-2 text-[var(--text-secondary)]">
              <span className="text-[var(--text-muted)] font-mono text-[11px]">Currently Targeting:</span>
              <span className="font-mono font-semibold text-[var(--text-primary)] flex items-center gap-1.5 bg-[var(--bg-surface)] px-2.5 py-1 rounded-md border border-[var(--border-subtle)]">
                <FolderGit2 className="h-3.5 w-3.5 text-[var(--brand)]" />
                {connectedRepo.fullName}
              </span>
              <span className="text-[var(--text-muted)]">•</span>
              <span className="font-mono text-[var(--success)] flex items-center gap-1 bg-[var(--success)]/10 px-2 py-0.5 rounded border border-[var(--success)]/30 text-[11px]">
                <GitBranch className="h-3 w-3" />
                {connectedRepo.selectedBranch}
              </span>
            </div>
            {connectedRepo.htmlUrl && (
              <a
                href={connectedRepo.htmlUrl}
                target="_blank"
                rel="noreferrer"
                className="text-[var(--brand-hover)] hover:underline flex items-center gap-1 text-[11px] font-mono"
              >
                <span>View on GitHub</span>
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        )}

        {/* 3. Navigation Tabs */}
        <div className="flex border-b border-[var(--border-subtle)] bg-[var(--bg-sidebar)] px-6 gap-2 overflow-x-auto">
          <button
            data-testid="tab-account"
            onClick={() => setActiveTab('account')}
            className={`flex items-center gap-2 py-2.5 px-3.5 text-xs font-semibold border-b-2 transition ${
              activeTab === 'account'
                ? 'border-[var(--brand)] text-[var(--brand-hover)] bg-[var(--brand-soft)] rounded-t-lg'
                : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]'
            }`}
          >
            <Github className="h-3.5 w-3.5" />
            <span>My GitHub Account</span>
            {user && (
              <span className="status-pill status-pill-verified text-[9px] py-0 px-1.5">
                Connected
              </span>
            )}
          </button>

          <button
            data-testid="tab-url"
            onClick={() => setActiveTab('url')}
            className={`flex items-center gap-2 py-2.5 px-3.5 text-xs font-semibold border-b-2 transition ${
              activeTab === 'url'
                ? 'border-[var(--brand)] text-[var(--brand-hover)] bg-[var(--brand-soft)] rounded-t-lg'
                : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]'
            }`}
          >
            <ExternalLink className="h-3.5 w-3.5" />
            <span>Direct GitHub URL</span>
          </button>

          <button
            data-testid="tab-starters"
            onClick={() => setActiveTab('starters')}
            className={`flex items-center gap-2 py-2.5 px-3.5 text-xs font-semibold border-b-2 transition ${
              activeTab === 'starters'
                ? 'border-[var(--brand)] text-[var(--brand-hover)] bg-[var(--brand-soft)] rounded-t-lg'
                : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]'
            }`}
          >
            <Sparkles className="h-3.5 w-3.5 text-[var(--warning)]" />
            <span>Curated Starter Repos</span>
          </button>

          <button
            data-testid="tab-local"
            onClick={() => setActiveTab('local')}
            className={`flex items-center gap-2 py-2.5 px-3.5 text-xs font-semibold border-b-2 transition ${
              activeTab === 'local'
                ? 'border-[var(--brand)] text-[var(--brand-hover)] bg-[var(--brand-soft)] rounded-t-lg'
                : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]'
            }`}
          >
            <Code2 className="h-3.5 w-3.5 text-[var(--cyan)]" />
            <span>Local Workspace</span>
          </button>
        </div>

        {/* 4. Tab Contents Area */}
        <div className="flex-1 p-6 overflow-y-auto min-h-[360px]">
          {/* TAB 1: MY GITHUB ACCOUNT */}
          {activeTab === 'account' && (
            <div>
              {!user ? (
                <div className="max-w-xl mx-auto py-2">
                  <div className="bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl p-6 text-center space-y-4">
                    <div className="h-11 w-11 rounded-xl bg-[var(--brand-soft)] border border-[var(--brand)]/30 flex items-center justify-center text-[var(--brand)] mx-auto">
                      <Key className="h-5 w-5" />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-[var(--text-primary)] font-mono uppercase">
                        Connect your GitHub Account
                      </h3>
                      <p className="text-xs text-[var(--text-secondary)] max-w-md mx-auto mt-1">
                        Enter a GitHub Personal Access Token (Classic or Fine-Grained) with{' '}
                        <code className="text-[var(--brand-hover)] bg-[var(--bg-root)] px-1 py-0.5 rounded border border-[var(--border-subtle)] font-mono">
                          repo
                        </code>{' '}
                        or{' '}
                        <code className="text-[var(--brand-hover)] bg-[var(--bg-root)] px-1 py-0.5 rounded border border-[var(--border-subtle)] font-mono">
                          public_repo
                        </code>{' '}
                        permissions to access repositories and create pull requests.
                      </p>
                    </div>

                    <form onSubmit={handleConnectToken} className="space-y-4 text-left pt-2">
                      <div>
                        <label className="block text-xs font-mono font-bold text-[var(--text-muted)] uppercase mb-1.5">
                          GitHub Personal Access Token (PAT)
                        </label>
                        <input
                          type="password"
                          value={patToken}
                          onChange={e => setPatToken(e.target.value)}
                          placeholder="ghp_xxxxxxxxxxxxxxxxxxxx or github_pat_xxxx..."
                          className="w-full bg-[var(--bg-root)] border border-[var(--border-subtle)] focus:border-[var(--brand)] rounded-lg px-3.5 py-2 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none font-mono"
                        />
                        {tokenInputError && (
                          <div className="flex items-center gap-1.5 text-[var(--danger)] text-xs mt-2 font-mono">
                            <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                            <span>{tokenInputError}</span>
                          </div>
                        )}
                      </div>

                      <div className="flex items-center justify-between pt-2">
                        <a
                          href="https://github.com/settings/tokens/new?scopes=repo,read:user&description=Loom%20Agentic%20Coding%20Harness"
                          target="_blank"
                          rel="noreferrer"
                          className="btn-tertiary text-xs p-0 gap-1"
                        >
                          <span>Generate Token on GitHub</span>
                          <ExternalLink className="h-3 w-3" />
                        </a>
                        <button
                          type="submit"
                          disabled={isAuthenticating}
                          className="btn-primary h-8 px-4 text-xs gap-1.5"
                        >
                          {isAuthenticating ? (
                            <>
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              <span>Verifying Token...</span>
                            </>
                          ) : (
                            <>
                              <Check className="h-3.5 w-3.5" />
                              <span>Connect Account</span>
                            </>
                          )}
                        </button>
                      </div>

                      <div className="pt-2 border-t border-[var(--border-subtle)] text-[11px] text-[var(--text-muted)] flex items-start gap-2">
                        <Lock className="h-3.5 w-3.5 text-[var(--success)] shrink-0 mt-0.5" />
                        <span>Security: Personal Access Tokens are held strictly in ephemeral session memory and are never persisted to localStorage or browser storage.</span>
                      </div>
                    </form>
                  </div>

                  <div className="text-center text-xs text-[var(--text-muted)] mt-4">
                    Prefer not to authenticate? You can use the{' '}
                    <button
                      onClick={() => setActiveTab('url')}
                      className="text-[var(--brand-hover)] hover:underline font-mono"
                    >
                      Direct GitHub URL
                    </button>{' '}
                    or{' '}
                    <button
                      onClick={() => setActiveTab('starters')}
                      className="text-[var(--brand-hover)] hover:underline font-mono"
                    >
                      Starter Repos
                    </button>{' '}
                    tabs without a token.
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Connected Profile Bar */}
                  <div className="bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl p-3.5 flex items-center justify-between flex-wrap gap-3">
                    <div className="flex items-center gap-3">
                      {user.avatar_url ? (
                        <Image
                          src={user.avatar_url}
                          alt={user.login}
                          width={36}
                          height={36}
                          className="h-9 w-9 rounded-full border border-[var(--brand)]/40"
                          unoptimized
                        />
                      ) : (
                        <div className="h-9 w-9 rounded-full bg-[var(--brand)] flex items-center justify-center font-bold text-white font-mono text-xs">
                          {user.login.slice(0, 2).toUpperCase()}
                        </div>
                      )}
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="text-xs font-bold text-[var(--text-primary)]">{user.name || user.login}</h4>
                          <span className="text-[11px] text-[var(--text-muted)] font-mono">@{user.login}</span>
                        </div>
                        <p className="text-[11px] text-[var(--text-muted)] flex items-center gap-2 mt-0.5">
                          <span>{user.public_repos} public repos</span>
                          {user.total_private_repos !== undefined && (
                            <>
                              <span>•</span>
                              <span>{user.total_private_repos} private repos</span>
                            </>
                          )}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => loadUserRepos()}
                        disabled={isLoadingRepos}
                        className="btn-secondary h-7 px-2.5 text-xs gap-1.5"
                        title="Refresh repositories"
                      >
                        <RefreshCw className={`h-3 w-3 ${isLoadingRepos ? 'animate-spin' : ''}`} />
                        <span>Refresh</span>
                      </button>

                      <button
                        onClick={disconnect}
                        className="btn-secondary h-7 px-2.5 text-xs gap-1.5 text-[var(--danger)] hover:border-[var(--danger)]/50"
                      >
                        <LogOut className="h-3 w-3" />
                        <span>Disconnect</span>
                      </button>
                    </div>
                  </div>

                  {/* Search and Filters */}
                  <div className="flex items-center gap-3 flex-wrap">
                    <div className="flex-1 min-w-[240px] relative">
                      <Search className="h-3.5 w-3.5 text-[var(--text-muted)] absolute left-3 top-1/2 -translate-y-1/2" />
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={e => setSearchQuery(e.target.value)}
                        placeholder="Search your repositories by name or description..."
                        className="w-full bg-[var(--bg-root)] border border-[var(--border-subtle)] focus:border-[var(--brand)] rounded-lg pl-8 pr-3 py-1.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none font-mono"
                      />
                    </div>
                    <div className="flex items-center bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg p-0.5 text-xs font-mono">
                      <button
                        onClick={() => setVisibilityFilter('all')}
                        className={`px-2.5 py-1 rounded text-[11px] font-semibold transition ${
                          visibilityFilter === 'all'
                            ? 'bg-[var(--brand)] text-white'
                            : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                        }`}
                      >
                        All ({userRepos.length})
                      </button>
                      <button
                        onClick={() => setVisibilityFilter('public')}
                        className={`px-2.5 py-1 rounded text-[11px] font-semibold transition ${
                          visibilityFilter === 'public'
                            ? 'bg-[var(--brand)] text-white'
                            : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                        }`}
                      >
                        Public
                      </button>
                      <button
                        onClick={() => setVisibilityFilter('private')}
                        className={`px-2.5 py-1 rounded text-[11px] font-semibold transition ${
                          visibilityFilter === 'private'
                            ? 'bg-[var(--brand)] text-white'
                            : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                        }`}
                      >
                        Private
                      </button>
                    </div>
                  </div>

                  {/* Repositories List Grid */}
                  {isLoadingRepos ? (
                    <div className="flex items-center justify-center py-12 gap-2 text-[var(--text-muted)] text-xs font-mono">
                      <Loader2 className="h-4 w-4 animate-spin text-[var(--brand)]" />
                      <span>Loading GitHub repositories...</span>
                    </div>
                  ) : filteredRepos.length === 0 ? (
                    <div className="text-center py-12 text-[var(--text-muted)] text-xs bg-[var(--bg-elevated)] rounded-xl border border-[var(--border-subtle)]">
                      No repositories found matching your query.
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[380px] overflow-y-auto pr-1">
                      {filteredRepos.map(repo => {
                        const isSelected = connectedRepo?.fullName === repo.full_name;
                        return (
                          <div
                            key={repo.id}
                            className={`p-3.5 rounded-xl border transition flex flex-col justify-between ${
                              isSelected
                                ? 'bg-[var(--brand-soft)] border-[var(--brand)]'
                                : 'bg-[var(--bg-elevated)] border-[var(--border-subtle)] hover:border-[var(--border-default)]'
                            }`}
                          >
                            <div>
                              <div className="flex items-start justify-between gap-2 mb-1.5">
                                <div className="flex items-center gap-1.5 font-bold text-xs text-[var(--text-primary)] truncate font-mono">
                                  {repo.private ? (
                                    <Lock className="h-3 w-3 text-[var(--warning)] shrink-0" />
                                  ) : (
                                    <Globe className="h-3 w-3 text-[var(--text-muted)] shrink-0" />
                                  )}
                                  <span className="truncate">{repo.full_name}</span>
                                </div>
                                <span className="text-[10px] bg-[var(--bg-surface)] text-[var(--text-muted)] px-1.5 py-0.2 rounded font-mono shrink-0 border border-[var(--border-subtle)]">
                                  {repo.default_branch}
                                </span>
                              </div>

                              <p className="text-[11px] text-[var(--text-secondary)] line-clamp-2 mb-3 min-h-[30px]">
                                {repo.description || 'No description provided.'}
                              </p>
                            </div>

                            <div className="flex items-center justify-between pt-2 border-t border-[var(--border-subtle)] text-[11px] text-[var(--text-muted)]">
                              <div className="flex items-center gap-3 font-mono text-[10px]">
                                {repo.language && (
                                  <span className="flex items-center gap-1 text-[var(--brand-hover)]">
                                    <span className="h-1.5 w-1.5 rounded-full bg-[var(--brand)]" />
                                    {repo.language}
                                  </span>
                                )}
                                <span className="flex items-center gap-1">
                                  <Star className="h-3 w-3 text-[var(--warning)]" />
                                  {repo.stargazers_count}
                                </span>
                                <span className="flex items-center gap-1">
                                  <GitFork className="h-3 w-3 text-[var(--text-muted)]" />
                                  {repo.forks_count}
                                </span>
                              </div>

                              <button
                                onClick={() => handleSelectUserRepo(repo)}
                                className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition flex items-center gap-1 ${
                                  isSelected
                                    ? 'bg-[var(--success)]/10 text-[var(--success)] border border-[var(--success)]/30'
                                    : 'btn-primary h-7 px-3 text-xs'
                                }`}
                              >
                                {isSelected ? (
                                  <>
                                    <Check className="h-3 w-3 stroke-[3]" />
                                    <span>Active</span>
                                  </>
                                ) : (
                                  <span>Connect</span>
                                )}
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* TAB 2: DIRECT GITHUB URL */}
          {activeTab === 'url' && (
            <div className="max-w-2xl mx-auto py-2 space-y-4">
              <div className="bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl p-5 space-y-3">
                <div className="flex items-center gap-2">
                  <ExternalLink className="h-4 w-4 text-[var(--brand)]" />
                  <h3 className="text-xs font-bold text-[var(--text-primary)] font-mono uppercase">
                    Connect by GitHub URL or Slug
                  </h3>
                </div>
                <p className="text-xs text-[var(--text-secondary)]">
                  Enter any public or private repository URL (e.g.{' '}
                  <code className="text-[var(--brand-hover)] bg-[var(--bg-root)] px-1 py-0.5 rounded border border-[var(--border-subtle)] font-mono">
                    https://github.com/fastapi/fastapi
                  </code>{' '}
                  or <code className="text-[var(--brand-hover)] bg-[var(--bg-root)] px-1 py-0.5 rounded border border-[var(--border-subtle)] font-mono">owner/repo</code>).
                </p>

                <form onSubmit={handleValidateDirectUrl} className="space-y-3 pt-1">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={directUrl}
                      onChange={e => setDirectUrl(e.target.value)}
                      placeholder="https://github.com/owner/repo or owner/repo"
                      className="flex-1 bg-[var(--bg-root)] border border-[var(--border-subtle)] focus:border-[var(--brand)] rounded-lg px-3 py-2 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none font-mono"
                    />
                    <button
                      type="submit"
                      disabled={isValidatingUrl}
                      className="btn-primary h-9 px-4 text-xs gap-1.5 shrink-0"
                    >
                      {isValidatingUrl ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          <span>Checking...</span>
                        </>
                      ) : (
                        <span>Inspect Repo</span>
                      )}
                    </button>
                  </div>

                  {urlError && (
                    <div className="flex items-center gap-1.5 text-[var(--danger)] text-xs font-mono">
                      <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                      <span>{urlError}</span>
                    </div>
                  )}
                </form>
              </div>

              {/* Inspected Repo Preview Card */}
              {validatedRepoData && (
                <div className="bg-[var(--bg-elevated)] border border-[var(--brand)]/40 rounded-xl p-5 shadow-xl space-y-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="h-9 w-9 rounded-xl bg-[var(--brand-soft)] border border-[var(--brand)]/30 flex items-center justify-center text-[var(--brand)]">
                        <FolderGit2 className="h-4 w-4" />
                      </div>
                      <div>
                        <h4 className="text-xs font-bold text-[var(--text-primary)] font-mono flex items-center gap-2">
                          {validatedRepoData.full_name}
                          {validatedRepoData.private ? (
                            <span className="status-pill status-pill-blocked text-[9px] py-0">
                              Private
                            </span>
                          ) : (
                            <span className="status-pill status-pill-verified text-[9px] py-0">
                              Public
                            </span>
                          )}
                        </h4>
                        <p className="text-xs text-[var(--text-secondary)] mt-0.5">
                          {validatedRepoData.description || 'No description available.'}
                        </p>
                      </div>
                    </div>

                    <a
                      href={validatedRepoData.html_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[var(--text-muted)] hover:text-[var(--text-primary)] p-1.5 rounded-lg hover:bg-[var(--bg-hover)] transition"
                      title="Open in GitHub"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  </div>

                  <div className="grid grid-cols-3 gap-3 text-xs font-mono bg-[var(--bg-root)] p-3 rounded-lg border border-[var(--border-subtle)]">
                    <div>
                      <span className="text-[var(--text-muted)] block text-[10px] uppercase">Language</span>
                      <span className="font-semibold text-[var(--brand-hover)]">
                        {validatedRepoData.language || 'Multiple'}
                      </span>
                    </div>
                    <div>
                      <span className="text-[var(--text-muted)] block text-[10px] uppercase">Stars</span>
                      <span className="font-semibold text-[var(--warning)]">
                        ★ {validatedRepoData.stargazers_count?.toLocaleString() || 0}
                      </span>
                    </div>
                    <div>
                      <span className="text-[var(--text-muted)] block text-[10px] uppercase">Default Branch</span>
                      <span className="text-[var(--success)] font-semibold">
                        {validatedRepoData.default_branch || 'main'}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-[var(--text-muted)] font-mono">Target Branch:</span>
                      <input
                        type="text"
                        value={urlBranch}
                        onChange={e => setUrlBranch(e.target.value)}
                        placeholder="main"
                        className="bg-[var(--bg-root)] border border-[var(--border-subtle)] rounded-lg px-2.5 py-1 text-xs text-[var(--text-primary)] font-mono w-28 focus:outline-none focus:border-[var(--brand)]"
                      />
                    </div>

                    <button
                      onClick={handleSelectDirectRepo}
                      className="btn-primary h-8 px-4 text-xs gap-1.5"
                    >
                      <Check className="h-3.5 w-3.5 stroke-[3]" />
                      <span>Set as Active Repository</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 3: CURATED STARTER REPOSITORIES */}
          {activeTab === 'starters' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-bold text-[var(--text-primary)] uppercase font-mono flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5 text-[var(--warning)]" />
                    Curated Template & Benchmark Repositories
                  </h3>
                  <p className="text-xs text-[var(--text-muted)] mt-0.5">
                    Connect immediately with popular repositories configured for agentic debugging and verification.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {POPULAR_STARTER_REPOS.map(starter => {
                  const isSelected = connectedRepo?.fullName === starter.fullName;
                  return (
                    <div
                      key={starter.fullName}
                      className={`p-4 rounded-xl border transition flex flex-col justify-between ${
                        isSelected
                          ? 'bg-[var(--brand-soft)] border-[var(--brand)]'
                          : 'bg-[var(--bg-elevated)] border border-[var(--border-subtle)] hover:border-[var(--border-default)]'
                      }`}
                    >
                      <div>
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <div>
                            <span className="text-[10px] bg-[var(--brand-soft)] text-[var(--brand-hover)] font-semibold px-2 py-0.5 rounded border border-[var(--brand)]/30 font-mono">
                              {starter.category}
                            </span>
                            <h4 className="text-xs font-bold text-[var(--text-primary)] mt-1.5 flex items-center gap-1.5 font-mono">
                              <FolderGit2 className="h-3.5 w-3.5 text-[var(--brand)] shrink-0" />
                              <span className="truncate">{starter.fullName}</span>
                            </h4>
                          </div>
                          <span className="text-xs font-mono text-[var(--warning)] flex items-center gap-1">
                            <Star className="h-3 w-3 fill-[var(--warning)]" />
                            {starter.stars}
                          </span>
                        </div>

                        <p className="text-xs text-[var(--text-secondary)] line-clamp-2 mb-3">
                          {starter.description}
                        </p>
                      </div>

                      <div className="flex items-center justify-between pt-2 border-t border-[var(--border-subtle)] text-xs">
                        <div className="flex items-center gap-2 text-[var(--text-muted)] font-mono text-[10px]">
                          <span className="flex items-center gap-1 text-[var(--brand-hover)]">
                            <span className="h-1.5 w-1.5 rounded-full bg-[var(--brand)]" />
                            {starter.language}
                          </span>
                          <span>•</span>
                          <span>branch: {starter.defaultBranch}</span>
                        </div>

                        <button
                          onClick={() => handleSelectStarter(starter)}
                          className={`px-3 py-1 rounded-lg text-xs font-semibold transition flex items-center gap-1 ${
                            isSelected
                              ? 'bg-[var(--success)]/10 text-[var(--success)] border border-[var(--success)]/30'
                              : 'btn-primary h-7 px-3 text-xs'
                          }`}
                        >
                          {isSelected ? (
                            <>
                              <Check className="h-3 w-3 stroke-[3]" />
                              <span>Active</span>
                            </>
                          ) : (
                            <>
                              <span>Connect</span>
                              <ArrowRight className="h-3 w-3" />
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* TAB 4: LOCAL WORKSPACE */}
          {activeTab === 'local' && (
            <div className="max-w-xl mx-auto py-2 space-y-4">
              <div className="bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl p-5 space-y-4">
                <div className="flex items-center gap-3">
                  <div className="h-9 w-9 rounded-xl bg-[var(--cyan)]/10 border border-[var(--cyan)]/30 flex items-center justify-center text-[var(--cyan)]">
                    <Code2 className="h-4 w-4" />
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-[var(--text-primary)] font-mono uppercase">
                      Local Workspace Directory
                    </h3>
                    <p className="text-xs text-[var(--text-muted)] mt-0.5">
                      Target local code repository on your filesystem with sandbox isolation.
                    </p>
                  </div>
                </div>

                <div className="space-y-4 pt-1">
                  <div>
                    <label className="block text-xs font-mono font-bold text-[var(--text-muted)] uppercase mb-1.5">
                      Filesystem Path
                    </label>
                    <input
                      type="text"
                      value={localPath}
                      onChange={e => setLocalPath(e.target.value)}
                      placeholder="."
                      className="w-full bg-[var(--bg-root)] border border-[var(--border-subtle)] focus:border-[var(--brand)] rounded-lg px-3 py-2 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none font-mono"
                    />
                    <span className="text-[11px] text-[var(--text-muted)] mt-1 block">
                      Use &quot;.&quot; for current workspace root or provide an absolute path.
                    </span>
                  </div>

                  <div>
                    <label className="block text-xs font-mono font-bold text-[var(--text-muted)] uppercase mb-1.5">
                      Sandbox Isolation Tier
                    </label>
                    <div className="grid grid-cols-2 gap-3">
                      <button
                        type="button"
                        onClick={() => setSandboxTier('A')}
                        className={`p-3 rounded-xl border text-left transition ${
                          sandboxTier === 'A'
                            ? 'bg-[var(--brand-soft)] border-[var(--brand)] text-[var(--text-primary)] ring-1 ring-[var(--brand)]/30'
                            : 'bg-[var(--bg-root)] border-[var(--border-subtle)] text-[var(--text-muted)] hover:border-[var(--border-default)]'
                        }`}
                      >
                        <div className="font-semibold text-xs text-[var(--brand-hover)] flex items-center justify-between mb-1 font-mono">
                          <span>Tier A: Git Worktree</span>
                          {sandboxTier === 'A' && <Check className="h-3 w-3 stroke-[3]" />}
                        </div>
                        <p className="text-[10px] text-[var(--text-secondary)]">
                          Lightweight atomic worktree isolation with snapshot rollback.
                        </p>
                      </button>

                      <button
                        type="button"
                        onClick={() => setSandboxTier('B')}
                        className={`p-3 rounded-xl border text-left transition ${
                          sandboxTier === 'B'
                            ? 'bg-[var(--brand-soft)] border-[var(--brand)] text-[var(--text-primary)] ring-1 ring-[var(--brand)]/30'
                            : 'bg-[var(--bg-root)] border-[var(--border-subtle)] text-[var(--text-muted)] hover:border-[var(--border-default)]'
                        }`}
                      >
                        <div className="font-semibold text-xs text-[var(--cyan)] flex items-center justify-between mb-1 font-mono">
                          <span>Tier B: MicroVM / Container</span>
                          {sandboxTier === 'B' && <Check className="h-3 w-3 stroke-[3]" />}
                        </div>
                        <p className="text-[10px] text-[var(--text-secondary)]">
                          Full kernel boundary egress enforcement & native dep isolation.
                        </p>
                      </button>
                    </div>
                  </div>

                  <div className="pt-2 flex justify-end">
                    <button
                      type="button"
                      onClick={handleConnectLocal}
                      className="btn-primary h-8 px-4 text-xs gap-2"
                    >
                      <Check className="h-3.5 w-3.5 stroke-[3]" />
                      <span>Connect Local Repository</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
