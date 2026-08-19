"use client";

import type { FormEvent, ReactNode } from 'react';
import { useEffect, useState } from 'react';
import {
  Key,
  Loader2,
  AlertCircle,
  Eye,
  EyeOff,
  Layers,
  Lock,
  ArrowRight,
  ShieldCheck,
  Cpu,
  GitBranch,
  Terminal,
} from 'lucide-react';

export function AuthGate({ children }: { children: ReactNode }) {
  const [token, setToken] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [checking, setChecking] = useState(false);
  const [sessionChecking, setSessionChecking] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
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
      const detail = params.get('detail');
      if (oauthErr) {
        if (oauthErr === 'unauthorized_email') {
          const email = params.get('email');
          setError(`Google account (${email || 'email'}) is not on the allowed whitelist.`);
        } else if (oauthErr === 'google_oauth_unconfigured') {
          setError('Google OAuth is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in environment variables.');
        } else if (oauthErr === 'invalid_oauth_state' || oauthErr === 'missing_oauth_parameters') {
          setError('OAuth session expired or invalid. Please try clicking "Sign in with Google" again.');
        } else if (oauthErr === 'invalid_client') {
          setError(`Google OAuth Client Secret is invalid or expired (invalid_client). Verify GOOGLE_CLIENT_SECRET in Vercel environment variables matches your Google Cloud Console credentials.${detail ? ` (${detail})` : ''}`);
        } else if (oauthErr === 'redirect_uri_mismatch') {
          setError(`Redirect URI mismatch (redirect_uri_mismatch). Make sure ${window.location.origin}/api/auth/callback/google is added to 'Authorized redirect URIs' in Google Cloud Console.${detail ? ` (${detail})` : ''}`);
        } else if (oauthErr === 'invalid_grant') {
          setError(`The Google authorization code was invalid, expired, or already used (invalid_grant). Please try signing in again.${detail ? ` (${detail})` : ''}`);
        } else if (oauthErr === 'unauthorized_client') {
          setError(`OAuth client unauthorized for this flow (unauthorized_client). Ensure Application type is set to 'Web application' in Google Cloud Console.${detail ? ` (${detail})` : ''}`);
        } else if (oauthErr === 'google_userinfo_failed') {
          setError('Failed to fetch user profile from Google API.');
        } else if (oauthErr === 'unverified_email') {
          setError('Your Google account email is not verified.');
        } else if (oauthErr === 'google_token_exchange_failed') {
          setError(`Google token exchange failed.${detail ? ` Detail: ${detail}` : ' Check GOOGLE_CLIENT_SECRET and Google Cloud Console settings.'}`);
        } else {
          setError(`Google Sign-In error: ${oauthErr}${detail ? ` (${detail})` : ''}`);
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
    if (!token.trim() || checking) return;
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
        throw new Error(body.detail || 'Authentication failed. Please verify your token.');
      }

      if (typeof window !== 'undefined') {
        localStorage.setItem('loom_auth_token', token.trim());
        localStorage.setItem('loom_api_key', token.trim());
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
      <main className="min-h-screen bg-[var(--bg-root)] text-[var(--text-primary)] flex items-center justify-center px-6 relative overflow-hidden">
        {/* Background glow */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-[var(--brand)]/15 rounded-full blur-[120px] pointer-events-none" aria-hidden="true" />
        {/* Animated ring pulses */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-72 h-72 border border-[var(--brand)]/10 rounded-full animate-ping opacity-20" aria-hidden="true" />
        <div className="relative z-10 flex flex-col items-center gap-4 font-mono">
          <div className="relative flex items-center justify-center">
            <div className="h-16 w-16 rounded-2xl border border-[var(--brand)]/40 bg-[var(--bg-surface)]/80 flex items-center justify-center shadow-2xl shadow-[var(--brand)]/20">
              <Layers className="h-7 w-7 text-[var(--brand)] animate-pulse" />
            </div>
            <div className="absolute -inset-3 rounded-3xl border border-[var(--brand)]/20 animate-ping opacity-25" />
          </div>
          <div className="text-center space-y-1">
            <p className="text-xs font-bold tracking-widest text-[var(--text-primary)] uppercase">LOOM CONTROL PLANE</p>
            <p className="text-[10px] text-[var(--text-muted)] tracking-wider uppercase flex items-center justify-center gap-1.5">
              <Loader2 className="h-3 w-3 animate-spin text-[var(--cyan)]" />
              Verifying session…
            </p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[var(--bg-root)] text-[var(--text-primary)] flex overflow-hidden relative">
      {/* ── LEFT PANEL: Animated Brand Hero ── */}
      <div className="hidden lg:flex flex-1 relative overflow-hidden flex-col justify-between p-10">
        {/* Gradient mesh background */}
        <div className="absolute inset-0 bg-gradient-to-br from-[var(--brand)]/20 via-[var(--bg-root)] to-[var(--cyan)]/10" aria-hidden="true" />
        <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-[var(--brand)]/15 rounded-full blur-[150px] -translate-y-1/2 translate-x-1/3 pointer-events-none" aria-hidden="true" />
        <div className="absolute bottom-0 left-0 w-[400px] h-[400px] bg-[var(--cyan)]/10 rounded-full blur-[120px] translate-y-1/2 -translate-x-1/4 pointer-events-none" aria-hidden="true" />

        {/* Grid pattern overlay */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:40px_40px] [mask-image:radial-gradient(ellipse_at_30%_50%,transparent_10%,black_70%)] pointer-events-none" aria-hidden="true" />

        <div className="relative z-10">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="h-11 w-11 rounded-xl bg-gradient-to-br from-[var(--brand)] to-[var(--brand-hover)] flex items-center justify-center shadow-lg shadow-[var(--brand)]/30">
              <Layers className="h-5 w-5 text-white" aria-hidden="true" />
            </div>
            <div>
              <span className="text-sm font-bold tracking-tight font-mono uppercase text-[var(--text-primary)]">LOOM</span>
              <span className="text-[9px] text-[var(--text-muted)] font-mono ml-1.5">v0.1.0</span>
            </div>
          </div>
        </div>

        {/* Center brand content */}
        <div className="relative z-10 max-w-sm">
          <div className="flex items-center gap-2 mb-4">
            <span className="text-[10px] font-mono font-bold text-[var(--brand-hover)] bg-[var(--brand-soft)] px-2 py-0.5 rounded border border-[var(--brand)]/30 uppercase tracking-wider">
              Autonomous Engineering
            </span>
          </div>
          <h1 className="text-3xl font-bold text-[var(--text-primary)] tracking-tight leading-tight mb-3">
            Control Plane for<br />
            <span className="bg-gradient-to-r from-[var(--brand-hover)] to-[var(--cyan)] bg-clip-text text-transparent">
              Agentic Coding
            </span>
          </h1>
          <p className="text-sm text-[var(--text-secondary)] leading-relaxed mb-8">
            Multi-agent DAG pipelines, cryptographic evidence bundles, and isolated sandbox execution — all orchestrated from a single control plane.
          </p>

          {/* Capability bullets */}
          <div className="space-y-3">
            {[
              { icon: GitBranch, label: '5-Stage DAG Orchestration', color: 'var(--brand)' },
              { icon: ShieldCheck, label: 'SHA-256 Hash-Chain Audit', color: 'var(--success)' },
              { icon: Terminal, label: 'Tier A/B/C Sandbox Isolation', color: 'var(--cyan)' },
              { icon: Cpu, label: 'Multi-Model Routing', color: 'var(--warning)' },
            ].map(cap => {
              const Icon = cap.icon;
              return (
                <div key={cap.label} className="flex items-center gap-3">
                  <div className="h-8 w-8 rounded-lg bg-[var(--bg-surface)]/60 border border-[var(--border-subtle)]/60 flex items-center justify-center backdrop-blur-sm" style={{ color: cap.color }}>
                    <Icon className="h-4 w-4" aria-hidden="true" />
                  </div>
                  <span className="text-sm text-[var(--text-secondary)] font-mono">{cap.label}</span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="relative z-10 text-[10px] font-mono text-[var(--text-muted)]">
          Loom Autonomous Engineering Harness · Tamper-Evident Runtime
        </div>
      </div>

      {/* ── RIGHT PANEL: Login Form ── */}
      <div className="flex-1 lg:max-w-[440px] flex flex-col justify-between relative px-6 sm:px-10 py-8">
        {/* Mobile brand header */}
        <div className="lg:hidden flex items-center gap-2.5 mb-8">
          <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-[var(--brand)] to-[var(--brand-hover)] flex items-center justify-center shadow-md shadow-[var(--brand)]/20">
            <Layers className="h-4 w-4 text-white" aria-hidden="true" />
          </div>
          <span className="text-sm font-bold tracking-tight font-mono uppercase text-[var(--text-primary)]">LOOM</span>
          <span className="text-[9px] text-[var(--text-muted)] font-mono">HARNESS</span>
        </div>

        <div className="flex-1 flex flex-col justify-center max-w-xs mx-auto w-full">
          {/* Form card with glass effect */}
          <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-surface)]/80 backdrop-blur-xl p-7 shadow-2xl shadow-black/30 relative overflow-hidden">
            {/* Top brand glow line */}
            <div className="absolute top-0 inset-x-0 h-[1px] bg-gradient-to-r from-transparent via-[var(--brand)] to-transparent opacity-70" aria-hidden="true" />

            {/* Brand Header */}
            <div className="flex items-start gap-3 mb-6">
              <div className="relative">
                <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-[var(--brand)] to-[var(--brand-hover)] flex items-center justify-center shadow-lg shadow-[var(--brand)]/25 shrink-0">
                  <Layers className="h-5 w-5 text-white" aria-hidden="true" />
                </div>
                <span className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full bg-[var(--success)] border-2 border-[var(--bg-surface)]" />
              </div>
              <div>
                <h1 className="text-sm font-bold tracking-tight text-[var(--text-primary)] uppercase font-mono">
                  Loom Dashboard
                </h1>
                <p className="text-[11px] text-[var(--text-muted)] mt-0.5 leading-relaxed">
                  Authenticate to access<br />the engineering control plane
                </p>
              </div>
            </div>

            {/* Error Alert Box */}
            {error && (
              <div
                className="mb-5 rounded-xl border border-[var(--danger)]/40 bg-[var(--danger)]/10 p-3.5 flex items-start gap-2.5 shadow-sm animate-fade-in"
                role="alert"
              >
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-[var(--danger)]" aria-hidden="true" />
                <div className="flex-1 text-[11px] text-[var(--danger)] font-mono leading-relaxed break-words">{error}</div>
              </div>
            )}

            {/* Sign-In Options */}
            <div className="space-y-3">
              <a
                href="/api/auth/google"
                className="w-full h-11 rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)]/80 hover:bg-[var(--bg-hover)] hover:border-[var(--brand)]/60 text-xs font-mono font-semibold text-[var(--text-primary)] transition-all duration-200 flex items-center justify-center gap-3 px-4 shadow-sm hover:shadow-[0_0_20px_rgba(124,92,255,0.12)] group"
              >
                <svg className="h-4 w-4 shrink-0 transition-transform group-hover:scale-105" viewBox="0 0 24 24" aria-hidden="true">
                  <path fill="#4285F4" d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17z" />
                  <path fill="#34A853" d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.36 7.33 24 12 24z" />
                  <path fill="#FBBC05" d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.18 0 9.99 0 12s.45 3.82 1.25 5.42l4.03-3.15z" />
                  <path fill="#EA4335" d="M12 4.75c1.77 0 3.35.61 4.05 1.16l3.04-3.04C17.95 1.18 15.24 0 12 0 7.33 0 3.26 2.64 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.93 6.72-4.93z" />
                </svg>
                <span>Sign in with Google</span>
                <ArrowRight className="h-3.5 w-3.5 ml-auto text-[var(--text-muted)] group-hover:text-[var(--text-primary)] group-hover:translate-x-0.5 transition-all opacity-60 group-hover:opacity-100" />
              </a>

              <button
                type="button"
                onClick={async () => {
                  setChecking(true);
                  setError(null);
                  try {
                    const res = await fetch('/api/auth/login', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ token: 'guest' }),
                    });
                    if (res.ok) {
                      setAuthenticated(true);
                    } else {
                      const data = await res.json().catch(() => ({}));
                      throw new Error(data.detail || 'Failed to enter workspace');
                    }
                  } catch (err) {
                    setError(err instanceof Error ? err.message : 'Login failed');
                  } finally {
                    setChecking(false);
                  }
                }}
                disabled={checking}
                className="w-full h-11 rounded-xl bg-gradient-to-r from-[var(--brand)] to-[var(--brand-hover)] text-white text-xs font-mono font-bold uppercase tracking-wider gap-2 shadow-lg shadow-[var(--brand)]/25 hover:shadow-[var(--brand)]/40 transition-all group flex items-center justify-center"
              >
                {checking ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>Connecting…</span>
                  </>
                ) : (
                  <>
                    <Layers className="h-3.5 w-3.5" />
                    <span>Enter Workspace</span>
                    <ArrowRight className="h-3.5 w-3.5 ml-auto opacity-60 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all" />
                  </>
                )}
              </button>
            </div>

            {/* Divider */}
            <div className="relative my-5 flex items-center justify-center">
              <div className="w-full border-t border-[var(--border-subtle)]" />
              <span className="absolute bg-[var(--bg-surface)] px-3 text-[10px] font-mono font-bold uppercase tracking-wider text-[var(--text-muted)] border border-[var(--border-subtle)]/70 rounded-full py-0.5">
                or continue with token
              </span>
            </div>

            {/* Token Sign-In Form */}
            <form onSubmit={login} className="space-y-4">
              <div>
                <label className="block text-[11px] font-mono font-bold uppercase text-[var(--text-muted)] mb-1.5 flex items-center gap-1.5">
                  <Key className="h-3 w-3 text-[var(--brand)]" aria-hidden="true" />
                  Dashboard Token / Root API Key
                </label>
                <div className="relative flex items-center">
                  <div className="absolute left-3.5 text-[var(--text-muted)] pointer-events-none">
                    <Lock className="h-3.5 w-3.5" aria-hidden="true" />
                  </div>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={token}
                    onChange={(event) => setToken(event.target.value)}
                    aria-label="Dashboard Token or Root API Key"
                    placeholder="Enter master token or API key"
                    autoComplete="current-password"
                    className="w-full rounded-xl border border-[var(--border-default)] bg-[var(--bg-root)] pl-9 pr-10 py-2.5 text-xs font-mono text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-muted)]/60 focus:border-[var(--brand)] focus:ring-2 focus:ring-[var(--brand)]/20"
                  />
                  {token.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition p-1"
                      aria-label={showPassword ? 'Hide token' : 'Show token'}
                      tabIndex={-1}
                    >
                      {showPassword
                        ? <EyeOff className="h-3.5 w-3.5" aria-hidden="true" />
                        : <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                      }
                    </button>
                  )}
                </div>
              </div>

              <button
                type="submit"
                disabled={checking || !token.trim()}
                aria-label="Authenticate with token"
                className="w-full h-11 rounded-xl bg-gradient-to-r from-[var(--brand)] to-[var(--brand-hover)] text-white text-xs font-mono font-bold uppercase tracking-wider gap-2 shadow-lg shadow-[var(--brand)]/25 hover:shadow-[var(--brand)]/40 transition-all group flex items-center justify-center disabled:opacity-50"
              >
                {checking ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>Authenticating…</span>
                  </>
                ) : (
                  <>
                    <Key className="h-3.5 w-3.5" />
                    <span>Sign in with Token</span>
                    <ArrowRight className="h-3.5 w-3.5 ml-auto opacity-60 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all" />
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Feature badges */}
          <div className="mt-6 grid grid-cols-2 gap-2 text-[10px] font-mono text-[var(--text-muted)]">
            {[
              { icon: GitBranch, label: '5-Stage DAG Engine', color: 'var(--brand)' },
              { icon: ShieldCheck, label: 'SHA-256 Hash Audit', color: 'var(--success)' },
              { icon: Terminal, label: 'Tier A/B/C Sandboxes', color: 'var(--cyan)' },
              { icon: Cpu, label: 'Multi-Model Routing', color: 'var(--warning)' },
            ].map(feat => {
              const Icon = feat.icon;
              return (
                <div key={feat.label} className="flex items-center gap-2 p-2.5 rounded-xl bg-[var(--bg-surface)]/60 border border-[var(--border-subtle)]/80 backdrop-blur-sm">
                  <Icon className="h-3.5 w-3.5 shrink-0" style={{ color: feat.color }} aria-hidden="true" />
                  <span className="truncate">{feat.label}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer */}
        <div className="hidden lg:flex items-center justify-between text-[10px] font-mono text-[var(--text-muted)] pt-6 px-1">
          <div className="flex items-center gap-2">
            <span>Loom Autonomous Engineering Harness</span>
            <span className="text-[var(--text-muted)]/40">·</span>
            <span className="text-[var(--text-secondary)]">Tamper-Evident Runtime</span>
          </div>
          <span>Confidential Access Only</span>
        </div>
      </div>
    </main>
  );
}
