"use client";

import React, { useState, useMemo } from 'react';
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
  Layers,
  ArrowRight,
} from 'lucide-react';
import { Github } from './GithubIcon';
import {
  useGitHub,
  POPULAR_STARTER_REPOS,
  GitHubRepo,
  ConnectedRepoState,
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
    setSelectedBranch,
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

    // Extract owner/repo from URL
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
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn"
      role="dialog"
      aria-modal="true"
      aria-labelledby="repo-modal-title"
    >
      <div
        className="relative w-full max-w-4xl bg-[#0F172A] border border-gray-800/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={e => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="px-6 py-5 border-b border-gray-800/80 bg-gradient-to-r from-gray-900 via-[#111827] to-gray-900 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white shadow-lg shadow-indigo-500/20">
              <Github className="h-5 w-5" />
            </div>
            <div>
              <h2 id="repo-modal-title" className="text-lg font-bold text-white flex items-center gap-2">
                Connect GitHub & Repositories
                <span className="text-[10px] bg-indigo-500/20 text-indigo-400 px-2 py-0.5 rounded-full border border-indigo-500/30 uppercase tracking-wider font-semibold">
                  Source Control
                </span>
              </h2>
              <p className="text-xs text-gray-400">
                Seamlessly target repositories, browse issues, and synthesize automated pull requests.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white p-2 rounded-lg hover:bg-gray-800/60 transition"
            aria-label="Close modal"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Current Active Connection Status Banner */}
        {connectedRepo && (
          <div className="bg-indigo-950/30 border-b border-indigo-500/20 px-6 py-2.5 flex items-center justify-between text-xs flex-wrap gap-2">
            <div className="flex items-center gap-2 text-gray-300">
              <span className="text-gray-400">Currently Targeting:</span>
              <span className="font-mono font-semibold text-indigo-300 flex items-center gap-1.5 bg-indigo-500/10 px-2.5 py-1 rounded-md border border-indigo-500/30">
                <FolderGit2 className="h-3.5 w-3.5 text-indigo-400" />
                {connectedRepo.fullName}
              </span>
              <span className="text-gray-500">•</span>
              <span className="font-mono text-emerald-400 flex items-center gap-1 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/30">
                <GitBranch className="h-3 w-3" />
                {connectedRepo.selectedBranch}
              </span>
            </div>
            {connectedRepo.htmlUrl && (
              <a
                href={connectedRepo.htmlUrl}
                target="_blank"
                rel="noreferrer"
                className="text-indigo-400 hover:text-indigo-300 flex items-center gap-1 hover:underline"
              >
                <span>View on GitHub</span>
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        )}

        {/* Navigation Tabs */}
        <div className="flex border-b border-gray-800 bg-gray-900/50 px-6 gap-2">
          <button
            data-testid="tab-account"
            onClick={() => setActiveTab('account')}
            className={`flex items-center gap-2 py-3 px-4 text-xs font-semibold border-b-2 transition ${
              activeTab === 'account'
                ? 'border-indigo-500 text-indigo-400 bg-indigo-500/10 rounded-t-lg'
                : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-800/40'
            }`}
          >
            <Github className="h-4 w-4" />
            <span>My GitHub Account</span>
            {user && (
              <span className="bg-emerald-500/20 text-emerald-400 text-[10px] px-1.5 py-0.5 rounded-full border border-emerald-500/30">
                Connected
              </span>
            )}
          </button>

          <button
            data-testid="tab-url"
            onClick={() => setActiveTab('url')}
            className={`flex items-center gap-2 py-3 px-4 text-xs font-semibold border-b-2 transition ${
              activeTab === 'url'
                ? 'border-indigo-500 text-indigo-400 bg-indigo-500/10 rounded-t-lg'
                : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-800/40'
            }`}
          >
            <ExternalLink className="h-4 w-4" />
            <span>Direct GitHub URL</span>
          </button>

          <button
            data-testid="tab-starters"
            onClick={() => setActiveTab('starters')}
            className={`flex items-center gap-2 py-3 px-4 text-xs font-semibold border-b-2 transition ${
              activeTab === 'starters'
                ? 'border-indigo-500 text-indigo-400 bg-indigo-500/10 rounded-t-lg'
                : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-800/40'
            }`}
          >
            <Sparkles className="h-4 w-4 text-amber-400" />
            <span>Curated Starter Repos</span>
          </button>

          <button
            data-testid="tab-local"
            onClick={() => setActiveTab('local')}
            className={`flex items-center gap-2 py-3 px-4 text-xs font-semibold border-b-2 transition ${
              activeTab === 'local'
                ? 'border-indigo-500 text-indigo-400 bg-indigo-500/10 rounded-t-lg'
                : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-800/40'
            }`}
          >
            <Code2 className="h-4 w-4 text-cyan-400" />
            <span>Local Workspace</span>
          </button>
        </div>

        {/* Tab Contents Area */}
        <div className="flex-1 p-6 overflow-y-auto min-h-[360px]">
          {/* 1. MY GITHUB ACCOUNT TAB */}
          {activeTab === 'account' && (
            <div>
              {!user ? (
                <div className="max-w-xl mx-auto py-4">
                  <div className="bg-gradient-to-br from-indigo-950/40 via-gray-900 to-gray-950 border border-indigo-500/20 rounded-2xl p-6 shadow-xl mb-6 text-center">
                    <div className="h-12 w-12 rounded-2xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 mx-auto mb-3 shadow-inner">
                      <Key className="h-6 w-6" />
                    </div>
                    <h3 className="text-base font-bold text-white mb-1">
                      Connect your GitHub Account
                    </h3>
                    <p className="text-xs text-gray-400 max-w-md mx-auto mb-5">
                      Enter a GitHub Personal Access Token (Classic or Fine-Grained) with{' '}
                      <code className="text-indigo-300 bg-indigo-950/60 px-1 py-0.5 rounded border border-indigo-800/60">repo</code>{' '}
                      or <code className="text-indigo-300 bg-indigo-950/60 px-1 py-0.5 rounded border border-indigo-800/60">public_repo</code>{' '}
                      permissions to access repositories and create pull requests.
                    </p>

                    <form onSubmit={handleConnectToken} className="space-y-4 text-left">
                      <div>
                        <label className="block text-xs font-semibold text-gray-300 mb-1.5">
                          GitHub Personal Access Token (PAT)
                        </label>
                        <input
                          type="password"
                          value={patToken}
                          onChange={e => setPatToken(e.target.value)}
                          placeholder="ghp_xxxxxxxxxxxxxxxxxxxx or github_pat_xxxx..."
                          className="w-full bg-gray-950 border border-gray-800 rounded-xl px-4 py-2.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
                        />
                        {tokenInputError && (
                          <div className="flex items-center gap-1.5 text-rose-400 text-xs mt-2">
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
                          className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 hover:underline"
                        >
                          <span>Generate Token on GitHub</span>
                          <ExternalLink className="h-3 w-3" />
                        </a>

                        <button
                          type="submit"
                          disabled={isAuthenticating}
                          className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white rounded-xl text-xs font-semibold transition disabled:opacity-50 shadow-lg shadow-indigo-600/30"
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
                    </form>
                  </div>

                  <div className="text-center text-xs text-gray-500">
                    Prefer not to authenticate? You can use the{' '}
                    <button
                      onClick={() => setActiveTab('url')}
                      className="text-indigo-400 hover:underline font-medium"
                    >
                      Direct GitHub URL
                    </button>{' '}
                    or{' '}
                    <button
                      onClick={() => setActiveTab('starters')}
                      className="text-indigo-400 hover:underline font-medium"
                    >
                      Starter Repos
                    </button>{' '}
                    tabs without a token.
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Connected Profile Bar */}
                  <div className="bg-gray-900/80 border border-gray-800 rounded-xl p-4 flex items-center justify-between flex-wrap gap-3">
                    <div className="flex items-center gap-3">
                      {user.avatar_url ? (
                        <img
                          src={user.avatar_url}
                          alt={user.login}
                          className="h-10 w-10 rounded-full border border-indigo-500/40 ring-2 ring-indigo-500/20"
                        />
                      ) : (
                        <div className="h-10 w-10 rounded-full bg-indigo-600 flex items-center justify-center font-bold text-white">
                          {user.login.slice(0, 2).toUpperCase()}
                        </div>
                      )}
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-bold text-white">{user.name || user.login}</h4>
                          <span className="text-xs text-gray-400 font-mono">@{user.login}</span>
                        </div>
                        <p className="text-xs text-gray-400 flex items-center gap-2">
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
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-xs transition"
                        title="Refresh repositories"
                      >
                        <RefreshCw className={`h-3.5 w-3.5 ${isLoadingRepos ? 'animate-spin' : ''}`} />
                        <span>Refresh</span>
                      </button>

                      <button
                        onClick={disconnect}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded-lg text-xs font-medium transition"
                      >
                        <LogOut className="h-3.5 w-3.5" />
                        <span>Disconnect</span>
                      </button>
                    </div>
                  </div>

                  {/* Search and Filters */}
                  <div className="flex items-center gap-3 flex-wrap">
                    <div className="flex-1 min-w-[240px] relative">
                      <Search className="h-4 w-4 text-gray-500 absolute left-3 top-2.5" />
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={e => setSearchQuery(e.target.value)}
                        placeholder="Search your repositories by name or description..."
                        className="w-full bg-gray-950 border border-gray-800 rounded-xl pl-9 pr-4 py-2 text-xs text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      />
                    </div>
                    <div className="flex items-center bg-gray-950 border border-gray-800 rounded-xl p-1 text-xs">
                      <button
                        onClick={() => setVisibilityFilter('all')}
                        className={`px-3 py-1 rounded-lg transition ${
                          visibilityFilter === 'all'
                            ? 'bg-indigo-600 text-white font-semibold'
                            : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        All ({userRepos.length})
                      </button>
                      <button
                        onClick={() => setVisibilityFilter('public')}
                        className={`px-3 py-1 rounded-lg transition ${
                          visibilityFilter === 'public'
                            ? 'bg-indigo-600 text-white font-semibold'
                            : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        Public
                      </button>
                      <button
                        onClick={() => setVisibilityFilter('private')}
                        className={`px-3 py-1 rounded-lg transition ${
                          visibilityFilter === 'private'
                            ? 'bg-indigo-600 text-white font-semibold'
                            : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        Private
                      </button>
                    </div>
                  </div>

                  {/* Repositories List */}
                  {isLoadingRepos ? (
                    <div className="flex items-center justify-center py-12 gap-2 text-gray-400 text-xs">
                      <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
                      <span>Loading your GitHub repositories...</span>
                    </div>
                  ) : filteredRepos.length === 0 ? (
                    <div className="text-center py-12 text-gray-500 text-xs bg-gray-900/40 rounded-xl border border-gray-800/60">
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
                                ? 'bg-indigo-950/40 border-indigo-500/60 shadow-lg shadow-indigo-500/10 ring-1 ring-indigo-500/40'
                                : 'bg-gray-900/60 border-gray-800 hover:border-gray-700 hover:bg-gray-900'
                            }`}
                          >
                            <div>
                              <div className="flex items-start justify-between gap-2 mb-1.5">
                                <div className="flex items-center gap-1.5 font-semibold text-xs text-white truncate">
                                  {repo.private ? (
                                    <Lock className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                                  ) : (
                                    <Globe className="h-3.5 w-3.5 text-gray-400 shrink-0" />
                                  )}
                                  <span className="truncate">{repo.full_name}</span>
                                </div>
                                <span className="text-[10px] bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded font-mono shrink-0">
                                  {repo.default_branch}
                                </span>
                              </div>

                              <p className="text-[11px] text-gray-400 line-clamp-2 mb-3 min-h-[30px]">
                                {repo.description || 'No description provided.'}
                              </p>
                            </div>

                            <div className="flex items-center justify-between pt-2 border-t border-gray-800/60 text-[11px] text-gray-400">
                              <div className="flex items-center gap-3">
                                {repo.language && (
                                  <span className="flex items-center gap-1 text-indigo-300">
                                    <span className="h-2 w-2 rounded-full bg-indigo-400" />
                                    {repo.language}
                                  </span>
                                )}
                                <span className="flex items-center gap-1">
                                  <Star className="h-3 w-3 text-amber-400" />
                                  {repo.stargazers_count}
                                </span>
                                <span className="flex items-center gap-1">
                                  <GitFork className="h-3 w-3 text-gray-400" />
                                  {repo.forks_count}
                                </span>
                              </div>

                              <button
                                onClick={() => handleSelectUserRepo(repo)}
                                className={`px-3 py-1 rounded-lg text-xs font-semibold transition flex items-center gap-1 ${
                                  isSelected
                                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                                    : 'bg-indigo-600 hover:bg-indigo-500 text-white'
                                }`}
                              >
                                {isSelected ? (
                                  <>
                                    <Check className="h-3 w-3" />
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

          {/* 2. DIRECT GITHUB URL TAB */}
          {activeTab === 'url' && (
            <div className="max-w-2xl mx-auto py-2 space-y-5">
              <div className="bg-gray-900/60 border border-gray-800 rounded-xl p-5">
                <h3 className="text-sm font-bold text-white mb-1 flex items-center gap-2">
                  <ExternalLink className="h-4 w-4 text-indigo-400" />
                  Connect by GitHub URL or Specifier
                </h3>
                <p className="text-xs text-gray-400 mb-4">
                  Enter any public or private repository URL (e.g.{' '}
                  <code className="text-indigo-300 bg-indigo-950/60 px-1 py-0.5 rounded">
                    https://github.com/fastapi/fastapi
                  </code>{' '}
                  or <code className="text-indigo-300 bg-indigo-950/60 px-1 py-0.5 rounded">owner/repo</code>).
                </p>

                <form onSubmit={handleValidateDirectUrl} className="space-y-4">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={directUrl}
                      onChange={e => setDirectUrl(e.target.value)}
                      placeholder="https://github.com/owner/repo or owner/repo"
                      className="flex-1 bg-gray-950 border border-gray-800 rounded-xl px-4 py-2.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
                    />
                    <button
                      type="submit"
                      disabled={isValidatingUrl}
                      className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold transition disabled:opacity-50 flex items-center gap-1.5 shrink-0"
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
                    <div className="flex items-center gap-1.5 text-rose-400 text-xs">
                      <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                      <span>{urlError}</span>
                    </div>
                  )}
                </form>
              </div>

              {/* Inspected Repo Preview Card */}
              {validatedRepoData && (
                <div className="bg-gradient-to-br from-indigo-950/50 via-gray-900 to-gray-900 border border-indigo-500/40 rounded-2xl p-5 shadow-xl animate-fadeIn space-y-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-300">
                        <FolderGit2 className="h-5 w-5" />
                      </div>
                      <div>
                        <h4 className="text-sm font-bold text-white flex items-center gap-2">
                          {validatedRepoData.full_name}
                          {validatedRepoData.private ? (
                            <span className="text-[10px] bg-amber-500/20 text-amber-400 px-2 py-0.5 rounded border border-amber-500/30">
                              Private
                            </span>
                          ) : (
                            <span className="text-[10px] bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded border border-emerald-500/30">
                              Public
                            </span>
                          )}
                        </h4>
                        <p className="text-xs text-gray-400">
                          {validatedRepoData.description || 'No description available.'}
                        </p>
                      </div>
                    </div>

                    <a
                      href={validatedRepoData.html_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-gray-400 hover:text-white p-2 rounded-lg hover:bg-gray-800 transition"
                      title="Open in GitHub"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  </div>

                  <div className="grid grid-cols-3 gap-3 text-xs bg-gray-950/60 p-3 rounded-xl border border-gray-800/80">
                    <div>
                      <span className="text-gray-500 block text-[10px] uppercase">Language</span>
                      <span className="font-semibold text-indigo-300">
                        {validatedRepoData.language || 'Multiple'}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500 block text-[10px] uppercase">Stars</span>
                      <span className="font-semibold text-amber-400">
                        ★ {validatedRepoData.stargazers_count?.toLocaleString() || 0}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500 block text-[10px] uppercase">Default Branch</span>
                      <span className="font-mono text-emerald-400 font-semibold">
                        {validatedRepoData.default_branch || 'main'}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-400">Target Branch:</span>
                      <input
                        type="text"
                        value={urlBranch}
                        onChange={e => setUrlBranch(e.target.value)}
                        placeholder="main"
                        className="bg-gray-950 border border-gray-800 rounded-lg px-2.5 py-1 text-xs text-white font-mono w-28 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                      />
                    </div>

                    <button
                      onClick={handleSelectDirectRepo}
                      className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white rounded-xl text-xs font-semibold transition shadow-lg shadow-emerald-600/30"
                    >
                      <Check className="h-4 w-4" />
                      <span>Set as Active Repository</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 3. CURATED STARTER REPOSITORIES TAB */}
          {activeTab === 'starters' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
                    <Sparkles className="h-4 w-4 text-amber-400" />
                    Curated Template & Benchmark Repositories
                  </h3>
                  <p className="text-xs text-gray-400">
                    Connect immediately with popular repositories configured for agentic debugging and verification.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {POPULAR_STARTER_REPOS.map(starter => {
                  const isSelected = connectedRepo?.fullName === starter.fullName;
                  return (
                    <div
                      key={starter.fullName}
                      className={`p-4 rounded-xl border transition flex flex-col justify-between ${
                        isSelected
                          ? 'bg-indigo-950/40 border-indigo-500/60 shadow-lg shadow-indigo-500/10 ring-1 ring-indigo-500/40'
                          : 'bg-gray-900/60 border-gray-800 hover:border-gray-700 hover:bg-gray-900'
                      }`}
                    >
                      <div>
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <div>
                            <span className="text-[10px] bg-indigo-500/20 text-indigo-300 font-semibold px-2 py-0.5 rounded-full border border-indigo-500/30">
                              {starter.category}
                            </span>
                            <h4 className="text-sm font-bold text-white mt-1.5 flex items-center gap-1.5">
                              <FolderGit2 className="h-4 w-4 text-indigo-400 shrink-0" />
                              <span className="truncate">{starter.fullName}</span>
                            </h4>
                          </div>
                          <span className="text-xs font-mono text-amber-400 flex items-center gap-1">
                            <Star className="h-3 w-3 fill-amber-400" />
                            {starter.stars}
                          </span>
                        </div>

                        <p className="text-xs text-gray-400 line-clamp-2 mb-4">
                          {starter.description}
                        </p>
                      </div>

                      <div className="flex items-center justify-between pt-2 border-t border-gray-800/80 text-xs">
                        <div className="flex items-center gap-2 text-gray-400 font-mono text-[11px]">
                          <span className="flex items-center gap-1 text-indigo-300">
                            <span className="h-2 w-2 rounded-full bg-indigo-400" />
                            {starter.language}
                          </span>
                          <span>•</span>
                          <span className="text-gray-500">branch: {starter.defaultBranch}</span>
                        </div>

                        <button
                          onClick={() => handleSelectStarter(starter)}
                          className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
                            isSelected
                              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                              : 'bg-indigo-600 hover:bg-indigo-500 text-white'
                          }`}
                        >
                          {isSelected ? (
                            <>
                              <Check className="h-3.5 w-3.5" />
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

          {/* 4. LOCAL WORKSPACE TAB */}
          {activeTab === 'local' && (
            <div className="max-w-xl mx-auto py-4 space-y-5">
              <div className="bg-gray-900/60 border border-gray-800 rounded-xl p-5">
                <div className="flex items-center gap-3 mb-4">
                  <div className="h-10 w-10 rounded-xl bg-cyan-600/20 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
                    <Code2 className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-white">Local Workspace Directory</h3>
                    <p className="text-xs text-gray-400">
                      Target local code repository on your filesystem with sandbox isolation.
                    </p>
                  </div>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 mb-1.5">
                      Filesystem Path
                    </label>
                    <input
                      type="text"
                      value={localPath}
                      onChange={e => setLocalPath(e.target.value)}
                      placeholder="."
                      className="w-full bg-gray-950 border border-gray-800 rounded-xl px-4 py-2.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-cyan-500 font-mono"
                    />
                    <span className="text-[11px] text-gray-500 mt-1 block">
                      Use &quot;.&quot; for current workspace root or provide an absolute path.
                    </span>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-gray-300 mb-1.5">
                      Sandbox Isolation Tier
                    </label>
                    <div className="grid grid-cols-2 gap-3">
                      <button
                        type="button"
                        onClick={() => setSandboxTier('A')}
                        className={`p-3 rounded-xl border text-left transition ${
                          sandboxTier === 'A'
                            ? 'bg-cyan-950/40 border-cyan-500/60 text-white ring-1 ring-cyan-500/40'
                            : 'bg-gray-950 border-gray-800 text-gray-400 hover:border-gray-700'
                        }`}
                      >
                        <div className="font-semibold text-xs text-cyan-300 flex items-center justify-between mb-1">
                          <span>Tier A: Git Worktree</span>
                          {sandboxTier === 'A' && <Check className="h-3 w-3" />}
                        </div>
                        <p className="text-[10px] text-gray-400">
                          Lightweight atomic worktree isolation with snapshot rollback.
                        </p>
                      </button>

                      <button
                        type="button"
                        onClick={() => setSandboxTier('B')}
                        className={`p-3 rounded-xl border text-left transition ${
                          sandboxTier === 'B'
                            ? 'bg-cyan-950/40 border-cyan-500/60 text-white ring-1 ring-cyan-500/40'
                            : 'bg-gray-950 border-gray-800 text-gray-400 hover:border-gray-700'
                        }`}
                      >
                        <div className="font-semibold text-xs text-cyan-300 flex items-center justify-between mb-1">
                          <span>Tier B: MicroVM / Container</span>
                          {sandboxTier === 'B' && <Check className="h-3 w-3" />}
                        </div>
                        <p className="text-[10px] text-gray-400">
                          Full kernel boundary egress enforcement & native dep isolation.
                        </p>
                      </button>
                    </div>
                  </div>

                  <div className="pt-2 flex justify-end">
                    <button
                      type="button"
                      onClick={handleConnectLocal}
                      className="px-5 py-2.5 bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white rounded-xl text-xs font-semibold transition shadow-lg shadow-cyan-600/20 flex items-center gap-2"
                    >
                      <Check className="h-4 w-4" />
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
