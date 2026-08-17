import { NextRequest, NextResponse } from 'next/server';

const GITHUB_API_BASE = 'https://api.github.com';

function getAuthHeader(req: NextRequest): string | null {
  const auth = req.headers.get('authorization');
  if (auth && auth.startsWith('Bearer ')) {
    return auth;
  }
  const token = req.nextUrl.searchParams.get('token') || process.env.GITHUB_TOKEN || process.env.NEXT_PUBLIC_GITHUB_TOKEN;
  if (token) {
    return `Bearer ${token}`;
  }
  return null;
}

export async function GET(req: NextRequest) {
  const action = req.nextUrl.searchParams.get('action') || 'user';
  const authHeader = getAuthHeader(req);

  const requestHeaders: Record<string, string> = {
    Accept: 'application/vnd.github.v3+json',
    'User-Agent': 'Loom-Agentic-Harness',
  };
  if (authHeader) {
    requestHeaders.Authorization = authHeader;
  }

  try {
    // 1. Action: user profile
    if (action === 'user') {
      if (!authHeader) {
        return NextResponse.json({ detail: 'No GitHub authentication token provided' }, { status: 401 });
      }

      const res = await fetch(`${GITHUB_API_BASE}/user`, { headers: requestHeaders });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        return NextResponse.json(
          { detail: errorData.message || 'Failed to authenticate with GitHub' },
          { status: res.status }
        );
      }

      const data = await res.json();
      return NextResponse.json(data);
    }

    // 2. Action: user repositories
    if (action === 'repos') {
      const perPage = req.nextUrl.searchParams.get('per_page') || '50';
      const sort = req.nextUrl.searchParams.get('sort') || 'updated';

      const endpoint = authHeader
        ? `${GITHUB_API_BASE}/user/repos?per_page=${perPage}&sort=${sort}&type=all`
        : `${GITHUB_API_BASE}/repositories?per_page=30`;

      const res = await fetch(endpoint, { headers: requestHeaders });
      if (!res.ok) {
        // Fallback default repos if rate limited or unauthenticated
        return NextResponse.json([
          {
            id: 1,
            name: 'Loom-Unified-Agentic-Coding-Harness',
            full_name: 'Harshid001/Loom-Unified-Agentic-Coding-Harness',
            owner: { login: 'Harshid001', avatar_url: 'https://github.com/identicons/app.png' },
            private: false,
            html_url: 'https://github.com/Harshid001/Loom-Unified-Agentic-Coding-Harness',
            description: 'Unified Agentic Coding Harness with 5-stage DAG pipeline & sandbox isolation.',
            default_branch: 'main',
            stargazers_count: 1200,
            forks_count: 85,
            language: 'Python',
            updated_at: new Date().toISOString(),
          },
          {
            id: 2,
            name: 'fastapi',
            full_name: 'fastapi/fastapi',
            owner: { login: 'fastapi', avatar_url: 'https://github.com/identicons/fastapi.png' },
            private: false,
            html_url: 'https://github.com/fastapi/fastapi',
            description: 'FastAPI framework, high performance, easy to learn, fast to code.',
            default_branch: 'master',
            stargazers_count: 78000,
            forks_count: 6500,
            language: 'Python',
            updated_at: new Date().toISOString(),
          },
        ]);
      }

      const data = await res.json();
      return NextResponse.json(data);
    }

    // 3. Action: repo details validation
    if (action === 'validate_repo') {
      const repo = req.nextUrl.searchParams.get('repo');
      if (!repo) {
        return NextResponse.json({ detail: 'Repository parameter is required' }, { status: 400 });
      }

      const res = await fetch(`${GITHUB_API_BASE}/repos/${repo}`, { headers: requestHeaders });
      if (!res.ok) {
        return NextResponse.json({ detail: `Repository ${repo} not found or inaccessible` }, { status: res.status });
      }

      const data = await res.json();
      return NextResponse.json(data);
    }

    // 4. Action: branches
    if (action === 'branches') {
      const repo = req.nextUrl.searchParams.get('repo');
      if (!repo) {
        return NextResponse.json([{ name: 'main' }, { name: 'master' }]);
      }

      const res = await fetch(`${GITHUB_API_BASE}/repos/${repo}/branches?per_page=30`, { headers: requestHeaders });
      if (!res.ok) {
        return NextResponse.json([{ name: 'main' }, { name: 'master' }]);
      }

      const data = await res.json();
      return NextResponse.json(data);
    }

    // 5. Action: issues
    if (action === 'issues') {
      const repo = req.nextUrl.searchParams.get('repo');
      const state = req.nextUrl.searchParams.get('state') || 'open';
      if (!repo) {
        return NextResponse.json([]);
      }

      const res = await fetch(`${GITHUB_API_BASE}/repos/${repo}/issues?state=${state}&per_page=30`, {
        headers: requestHeaders,
      });

      if (!res.ok) {
        // Return starter mock issues for demonstration if GitHub API fails
        return NextResponse.json([
          {
            id: 101,
            number: 14,
            title: 'Fix token budget estimation edge case in context manager',
            body: 'When processing large AST graphs with deep recursion, token limits can overflow.',
            state: 'open',
            html_url: `https://github.com/${repo}/issues/14`,
            user: { login: 'agent-maintainer', avatar_url: 'https://github.com/identicons/app.png' },
            labels: [
              { id: 1, name: 'bug', color: 'd73a4a' },
              { id: 2, name: 'context-manager', color: '0075ca' },
            ],
            comments: 3,
            created_at: new Date(Date.now() - 3600000 * 24).toISOString(),
            updated_at: new Date().toISOString(),
          },
          {
            id: 102,
            number: 18,
            title: 'Implement cryptographic state verification for OAuth redirects',
            body: 'Ensure nonce and state HMAC matching before accepting callback token payloads.',
            state: 'open',
            html_url: `https://github.com/${repo}/issues/18`,
            user: { login: 'sec-team', avatar_url: 'https://github.com/identicons/sec.png' },
            labels: [
              { id: 3, name: 'security', color: 'b60205' },
              { id: 4, name: 'enhancement', color: 'a2eeef' },
            ],
            comments: 1,
            created_at: new Date(Date.now() - 3600000 * 12).toISOString(),
            updated_at: new Date().toISOString(),
          },
          {
            id: 103,
            number: 22,
            title: 'Optimize AST call graph dependency indexer for Python & TypeScript',
            body: 'Speed up Tree-Sitter symbol resolution on repos with >10,000 files.',
            state: 'open',
            html_url: `https://github.com/${repo}/issues/22`,
            user: { login: 'perf-eng', avatar_url: 'https://github.com/identicons/perf.png' },
            labels: [{ id: 5, name: 'performance', color: 'fbca04' }],
            comments: 5,
            created_at: new Date(Date.now() - 3600000 * 6).toISOString(),
            updated_at: new Date().toISOString(),
          },
        ]);
      }

      const data = await res.json();
      // Filter out pull requests from issues endpoint if any
      const issuesOnly = Array.isArray(data) ? data.filter((item: any) => !item.pull_request) : [];
      return NextResponse.json(issuesOnly);
    }

    return NextResponse.json({ detail: 'Unsupported action' }, { status: 400 });
  } catch (error: any) {
    return NextResponse.json({ detail: error.message || 'Internal GitHub proxy error' }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  const action = req.nextUrl.searchParams.get('action') || 'pr';
  const authHeader = getAuthHeader(req);

  if (!authHeader) {
    return NextResponse.json({ detail: 'GitHub authentication token required for write actions' }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));

  if (action === 'pr') {
    const { repo, title, body: prBody, head, base = 'main' } = body;
    if (!repo || !title || !head) {
      return NextResponse.json({ detail: 'Missing required parameters: repo, title, head' }, { status: 400 });
    }

    try {
      const res = await fetch(`${GITHUB_API_BASE}/repos/${repo}/pulls`, {
        method: 'POST',
        headers: {
          Accept: 'application/vnd.github.v3+json',
          'User-Agent': 'Loom-Agentic-Harness',
          Authorization: authHeader,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title,
          body: prBody || 'Automated PR generated by Loom Agentic Harness verification.',
          head,
          base,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        return NextResponse.json(
          { detail: err.message || 'Failed to create Pull Request on GitHub' },
          { status: res.status }
        );
      }

      const prData = await res.json();
      return NextResponse.json(prData, { status: 201 });
    } catch (err: any) {
      return NextResponse.json({ detail: err.message || 'Failed to communicate with GitHub API' }, { status: 500 });
    }
  }

  return NextResponse.json({ detail: 'Unsupported POST action' }, { status: 400 });
}
