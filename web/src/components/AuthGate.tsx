"use client";

import type { FormEvent, ReactNode } from 'react';
import { useEffect, useState } from 'react';

export function AuthGate({ children }: { children: ReactNode }) {
  const [token, setToken] = useState('');
  const [authenticated, setAuthenticated] = useState(false);
  const [checking, setChecking] = useState(false);
  const [sessionChecking, setSessionChecking] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Check if user already has an active session
    let mounted = true;
    async function checkSession() {
      try {
        const res = await fetch('/api/auth/session');
        if (res.ok) {
          const data = await res.json().catch(() => ({}));
          if (data.authenticated && mounted) {
            setAuthenticated(true);
            return;
          }
        }
      } catch {
        // Session check failed, fall through to login screen
      } finally {
        if (mounted) {
          setSessionChecking(false);
        }
      }
    }

    // Check for query param OAuth errors
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const oauthErr = params.get('error');
      if (oauthErr) {
        if (oauthErr === 'unauthorized_email') {
          const email = params.get('email');
          setError(`Google account (${email || 'email'}) is not on the allowed whitelist.`);
        } else if (oauthErr === 'google_oauth_unconfigured') {
          setError('Google OAuth is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.');
        } else if (oauthErr === 'invalid_oauth_state') {
          setError('Invalid OAuth session state. Please try signing in again.');
        } else {
          setError(`Google Sign-In error: ${oauthErr}`);
        }
      }
    }

    checkSession();
    return () => {
      mounted = false;
    };
  }, []);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setChecking(true);
    setError(null);

    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || 'Authentication failed');
      }

      setAuthenticated(true);
      setToken('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed');
    } finally {
      setChecking(false);
    }
  }

  if (authenticated) return <>{children}</>;

  if (sessionChecking) {
    return (
      <main className="min-h-screen bg-[#0B0F19] text-gray-100 flex items-center justify-center px-6">
        <div className="flex flex-col items-center gap-3">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
          <p className="text-xs text-gray-400">Verifying session…</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#0B0F19] text-gray-100 flex items-center justify-center px-6 selection:bg-indigo-500 selection:text-white">
      <div className="w-full max-w-md rounded-2xl border border-gray-800 bg-[#111827] p-8 shadow-2xl">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-700 flex items-center justify-center shadow-lg shadow-indigo-500/20 text-white font-bold">
            L
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white">Loom Dashboard</h1>
            <p className="text-xs text-gray-400">Sign in to manage and monitor agentic workflows</p>
          </div>
        </div>

        {error && (
          <div className="mt-5 rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-xs text-red-400 flex items-start gap-2" role="alert">
            <span className="font-semibold shrink-0">Error:</span>
            <span>{error}</span>
          </div>
        )}

        {/* Google Sign-In Option */}
        <div className="mt-6">
          <a
            href="/api/auth/google"
            className="flex w-full items-center justify-center gap-3 rounded-xl border border-gray-700 bg-gray-900/90 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-gray-800 hover:border-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
          >
            <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24">
              <path
                fill="#4285F4"
                d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17z"
              />
              <path
                fill="#34A853"
                d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.36 7.33 24 12 24z"
              />
              <path
                fill="#FBBC05"
                d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.18 0 9.99 0 12s.45 3.82 1.25 5.42l4.03-3.15z"
              />
              <path
                fill="#EA4335"
                d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.33 0 3.26 2.64 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.98 6.72-4.98z"
              />
            </svg>
            <span>Sign in with Google</span>
          </a>
        </div>

        <div className="relative my-6 flex items-center justify-center">
          <div className="w-full border-t border-gray-800" />
          <span className="absolute bg-[#111827] px-3 text-[11px] font-medium uppercase tracking-wider text-gray-500">
            or continue with token
          </span>
        </div>

        {/* Token Sign-In Form */}
        <form onSubmit={login} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1.5">
              Dashboard Token / Root API Key
            </label>
            <input
              type="password"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="Enter master token or API key"
              autoComplete="current-password"
              className="w-full rounded-xl border border-gray-700 bg-gray-950 px-3.5 py-2.5 text-sm text-gray-100 outline-none transition placeholder:text-gray-600 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <button
            type="submit"
            disabled={checking || !token.trim()}
            className="w-full rounded-xl bg-indigo-600 py-2.5 text-sm font-semibold text-white shadow-md shadow-indigo-600/20 transition hover:bg-indigo-500 disabled:opacity-40"
          >
            {checking ? 'Authenticating…' : 'Sign in with Token'}
          </button>
        </form>
      </div>
    </main>
  );
}

