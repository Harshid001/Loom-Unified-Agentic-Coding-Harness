"use client";

import { useState, useEffect, useCallback } from 'react';

export interface GitHubUser {
  login: string;
  name: string | null;
  avatar_url: string;
  html_url: string;
  public_repos: number;
  total_private_repos?: number;
  bio?: string | null;
}

export interface GitHubRepo {
  id: number;
  name: string;
  full_name: string;
  owner: {
    login: string;
    avatar_url: string;
  };
  private: boolean;
  html_url: string;
  description: string | null;
  default_branch: string;
  stargazers_count: number;
  forks_count: number;
  language: string | null;
  updated_at: string;
}

export interface GitHubIssue {
  id: number;
  number: number;
  title: string;
  body: string | null;
  state: 'open' | 'closed';
  html_url: string;
  user: {
    login: string;
    avatar_url: string;
  };
  labels: Array<{
    id: number;
    name: string;
    color: string;
    description?: string | null;
  }>;
  comments: number;
  created_at: string;
  updated_at: string;
}

export interface GitHubBranch {
  name: string;
  commit: {
    sha: string;
    url: string;
  };
  protected?: boolean;
}

export interface ConnectedRepoState {
  fullName: string;
  name: string;
  owner: string;
  defaultBranch: string;
  selectedBranch: string;
  htmlUrl: string;
  isPrivate: boolean;
  description?: string | null;
  language?: string | null;
  stars?: number;
}

// Security: GitHub PATs are held strictly in ephemeral in-memory state and are never persisted to localStorage.
const STORAGE_KEY_REPO = 'loom_connected_repo';
const STORAGE_KEY_USER = 'loom_github_user';

export const POPULAR_STARTER_REPOS: Array<{
  fullName: string;
  name: string;
  owner: string;
  description: string;
  language: string;
  defaultBranch: string;
  stars: string;
  category: string;
}> = [
  {
    fullName: 'Harshid001/Loom-Unified-Agentic-Coding-Harness',
    name: 'Loom-Unified-Agentic-Coding-Harness',
    owner: 'Harshid001',
    description: 'Unified Agentic Coding Harness with 5-stage DAG pipeline, sandbox isolation & cryptographic verification.',
    language: 'Python',
    defaultBranch: 'main',
    stars: '1.2k',
    category: 'Featured Harness',
  },
  {
    fullName: 'fastapi/fastapi',
    name: 'fastapi',
    owner: 'fastapi',
    description: 'FastAPI framework, high performance, easy to learn, fast to code, ready for production.',
    language: 'Python',
    defaultBranch: 'master',
    stars: '78k',
    category: 'Backend Framework',
  },
  {
    fullName: 'vercel/next.js',
    name: 'next.js',
    owner: 'vercel',
    description: 'The React Framework for the Web with App Router and server components.',
    language: 'TypeScript',
    defaultBranch: 'canary',
    stars: '125k',
    category: 'Full-Stack Web',
  },
  {
    fullName: 'pallets/flask',
    name: 'flask',
    owner: 'pallets',
    description: 'The Python micro framework for building web applications.',
    language: 'Python',
    defaultBranch: 'main',
    stars: '67k',
    category: 'Web Framework',
  },
  {
    fullName: 'psf/black',
    name: 'black',
    owner: 'psf',
    description: 'The uncompromising Python code formatter.',
    language: 'Python',
    defaultBranch: 'main',
    stars: '38k',
    category: 'Tooling',
  },
  {
    fullName: 'pydantic/pydantic',
    name: 'pydantic',
    owner: 'pydantic',
    description: 'Data validation using Python type hints.',
    language: 'Python',
    defaultBranch: 'main',
    stars: '21k',
    category: 'Data Validation',
  },
];

export function useGitHub() {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<GitHubUser | null>(null);
  const [userRepos, setUserRepos] = useState<GitHubRepo[]>([]);
  const [connectedRepo, setConnectedRepo] = useState<ConnectedRepoState | null>(null);
  const [repoIssues, setRepoIssues] = useState<GitHubIssue[]>([]);
  const [repoBranches, setRepoBranches] = useState<GitHubBranch[]>([]);
  const [isLoadingUser, setIsLoadingUser] = useState<boolean>(false);
  const [isLoadingRepos, setIsLoadingRepos] = useState<boolean>(false);
  const [isLoadingIssues, setIsLoadingIssues] = useState<boolean>(false);
  const [isLoadingBranches, setIsLoadingBranches] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Initialize and proactively purge any legacy tokens from localStorage
  useEffect(() => {
    if (typeof window === 'undefined') return;

    try {
      // Proactive cleanup: purge any legacy unencrypted PAT from localStorage
      if (localStorage.getItem('loom_github_token')) {
        localStorage.removeItem('loom_github_token');
      }

      const savedUserStr = localStorage.getItem(STORAGE_KEY_USER);
      if (savedUserStr) {
        setUser(JSON.parse(savedUserStr));
      }

      const savedRepoStr = localStorage.getItem(STORAGE_KEY_REPO);
      if (savedRepoStr) {
        setConnectedRepo(JSON.parse(savedRepoStr));
      } else {
        // Default to Loom repo as starter
        setConnectedRepo({
          fullName: 'Harshid001/Loom-Unified-Agentic-Coding-Harness',
          name: 'Loom-Unified-Agentic-Coding-Harness',
          owner: 'Harshid001',
          defaultBranch: 'main',
          selectedBranch: 'main',
          htmlUrl: 'https://github.com/Harshid001/Loom-Unified-Agentic-Coding-Harness',
          isPrivate: false,
          description: 'Unified Agentic Coding Harness with 5-stage DAG pipeline & sandbox isolation.',
          language: 'Python',
        });
      }
    } catch {
      // Storage error handling
    }
  }, []);

  // Fetch user profile with token (stored strictly in ephemeral React state)
  const authenticate = useCallback(async (authToken: string) => {
    setIsLoadingUser(true);
    setError(null);
    try {
      const cleanToken = authToken.trim();
      const res = await fetch('/api/github?action=user', {
        headers: {
          Authorization: `Bearer ${cleanToken}`,
        },
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Invalid GitHub token or authentication failed');
      }

      const userData: GitHubUser = await res.json();
      setToken(cleanToken);
      setUser(userData);

      if (typeof window !== 'undefined') {
        localStorage.setItem(STORAGE_KEY_USER, JSON.stringify(userData));
      }

      // Load repos immediately after auth
      loadUserRepos(cleanToken);
      return userData;
    } catch (err: any) {
      setError(err.message || 'Failed to authenticate with GitHub');
      throw err;
    } finally {
      setIsLoadingUser(false);
    }
  }, []);

  // Disconnect GitHub
  const disconnect = useCallback(() => {
    setToken(null);
    setUser(null);
    setUserRepos([]);
    if (typeof window !== 'undefined') {
      localStorage.removeItem('loom_github_token');
      localStorage.removeItem(STORAGE_KEY_USER);
    }
  }, []);

  // Load User Repositories
  const loadUserRepos = useCallback(async (authToken?: string) => {
    const activeToken = authToken || token;
    setIsLoadingRepos(true);
    try {
      const headers: Record<string, string> = {};
      if (activeToken) {
        headers.Authorization = `Bearer ${activeToken}`;
      }

      const res = await fetch('/api/github?action=repos', { headers });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setUserRepos(data);
        }
      }
    } catch {
      // Ignore network errors on background repo refresh
    } finally {
      setIsLoadingRepos(false);
    }
  }, [token]);

  // Load Branches for a repository
  const loadBranches = useCallback(async (repoFullName: string) => {
    setIsLoadingBranches(true);
    try {
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;

      const res = await fetch(`/api/github?action=branches&repo=${encodeURIComponent(repoFullName)}`, {
        headers,
      });

      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setRepoBranches(data);
          return data;
        }
      }
      return [];
    } catch {
      return [];
    } finally {
      setIsLoadingBranches(false);
    }
  }, [token]);

  // Load Issues for connected repository
  const loadIssues = useCallback(async (repoFullName: string) => {
    setIsLoadingIssues(true);
    try {
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;

      const res = await fetch(`/api/github?action=issues&repo=${encodeURIComponent(repoFullName)}`, {
        headers,
      });

      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setRepoIssues(data);
          return data;
        }
      }
      return [];
    } catch {
      return [];
    } finally {
      setIsLoadingIssues(false);
    }
  }, [token]);

  // Connect a specific repository
  const connectRepository = useCallback((repo: {
    fullName: string;
    name?: string;
    owner?: string;
    defaultBranch?: string;
    selectedBranch?: string;
    htmlUrl?: string;
    isPrivate?: boolean;
    description?: string | null;
    language?: string | null;
    stars?: number;
  }) => {
    const parts = repo.fullName.split('/');
    const owner = repo.owner || parts[0] || 'unknown';
    const name = repo.name || parts[1] || repo.fullName;
    const branch = repo.selectedBranch || repo.defaultBranch || 'main';

    const newConnected: ConnectedRepoState = {
      fullName: repo.fullName,
      name,
      owner,
      defaultBranch: repo.defaultBranch || 'main',
      selectedBranch: branch,
      htmlUrl: repo.htmlUrl || `https://github.com/${repo.fullName}`,
      isPrivate: repo.isPrivate || false,
      description: repo.description,
      language: repo.language,
      stars: repo.stars,
    };

    setConnectedRepo(newConnected);
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEY_REPO, JSON.stringify(newConnected));
    }

    // Refresh branches and issues for this repo
    loadBranches(repo.fullName);
    loadIssues(repo.fullName);
  }, [loadBranches, loadIssues]);

  // Change selected branch
  const setSelectedBranch = useCallback((branch: string) => {
    setConnectedRepo(prev => {
      if (!prev) return null;
      const updated = { ...prev, selectedBranch: branch };
      if (typeof window !== 'undefined') {
        localStorage.setItem(STORAGE_KEY_REPO, JSON.stringify(updated));
      }
      return updated;
    });
  }, []);

  // Create GitHub Pull Request
  const createPullRequest = useCallback(async (params: {
    title: string;
    body: string;
    head: string;
    base?: string;
    repoFullName?: string;
  }) => {
    const targetRepo = params.repoFullName || connectedRepo?.fullName;
    if (!targetRepo) throw new Error('No target repository selected');
    if (!token) throw new Error('GitHub token required to create a Pull Request');

    const res = await fetch('/api/github?action=pr', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        repo: targetRepo,
        title: params.title,
        body: params.body,
        head: params.head,
        base: params.base || connectedRepo?.selectedBranch || 'main',
      }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to create GitHub Pull Request');
    }

    return await res.json();
  }, [token, connectedRepo]);

  // Initial load of issues and branches on mount if repo is selected
  useEffect(() => {
    if (connectedRepo?.fullName) {
      loadBranches(connectedRepo.fullName);
      loadIssues(connectedRepo.fullName);
    }
  }, [connectedRepo?.fullName, loadBranches, loadIssues]);

  return {
    token,
    user,
    userRepos,
    connectedRepo,
    repoIssues,
    repoBranches,
    isLoadingUser,
    isLoadingRepos,
    isLoadingIssues,
    isLoadingBranches,
    error,
    authenticate,
    disconnect,
    loadUserRepos,
    loadBranches,
    loadIssues,
    connectRepository,
    setSelectedBranch,
    createPullRequest,
  };
}
