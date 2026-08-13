"use client";

import { FormEvent, useState } from 'react';

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState('');
  const [authenticated, setAuthenticated] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function login(event: FormEvent) {
    event.preventDefault();
    setChecking(true);
    setError(null);
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
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

  return (
    <main className="min-h-screen bg-[#0B0F19] text-gray-100 flex items-center justify-center px-6">
      <form onSubmit={login} className="w-full max-w-md rounded-2xl border border-gray-800 bg-[#111827] p-6 shadow-2xl">
        <h1 className="text-xl font-semibold">Loom Dashboard</h1>
        <p className="mt-2 text-sm text-gray-400">Authenticate with the configured dashboard token.</p>
        <input
          type="password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          placeholder="Dashboard token"
          autoComplete="current-password"
          className="mt-5 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm outline-none focus:border-indigo-500"
        />
        {error && <p className="mt-3 text-xs text-red-400" role="alert">{error}</p>}
        <button
          type="submit"
          disabled={checking || !token.trim()}
          className="mt-4 w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-40"
        >
          {checking ? 'Authenticating…' : 'Sign in'}
        </button>
      </form>
    </main>
  );
}
