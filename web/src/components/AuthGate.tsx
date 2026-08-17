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
        {/* Background glow effects */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-[var(--brand)]/15 rounded-full blur-[120px] pointer-events-none" />
        <div className="relative z-10 flex flex-col items-center gap-4 font-mono">
          <div className="relative flex items-center justify-center">
            <div className="h-14 w-14 rounded-2xl border border-[var(--brand)]/40 bg-[var(--bg-surface)]/80 flex items-center justify-center shadow-2xl shadow-[var(--brand)]/20">
              <Layers className="h-6 w-6 text-[var(--brand)] animate-pulse" />
            </div>
            <div className="absolute -inset-2 rounded-2xl border border-[var(--brand)]/20 animate-ping opacity-25" />
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
    <main className="min-h-screen bg-[var(--bg-root)] text-[var(--text-primary)] flex flex-col justify-between relative overflow-hidden px-4 sm:px-6 py-8 selection:bg-[var(--brand)] selection:text-white">
      {/* Dynamic ambient background glows */}
      <div className="absolute top-[-10%] left-1/2 -translate-x-1/2 w-[700px] h-[400px] bg-gradient-to-b from-[var(--brand)]/20 via-[var(--cyan)]/5 to-transparent rounded-full blur-[130px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-5%] w-[500px] h-[350px] bg-[var(--brand)]/10 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute top-[40%] left-[-10%] w-[450px] h-[300px] bg-[var(--cyan)]/5 rounded-full blur-[130px] pointer-events-none" />

      {/* Grid overlay */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:32px_32px] pointer-events-none [mask-image:radial-gradient(ellipse_at_center,transparent_10%,black_80%)]" />

      {/* TOP SYSTEM STATUS BAR */}
      <header className="relative z-10 w-full max-w-5xl mx-auto flex items-center justify-between py-2 px-2 text-xs font-mono">
        <div className="flex items-center gap-2.5">
          <div className="h-6 w-6 rounded-lg bg-[var(--brand)]/20 border border-[var(--brand)]/40 flex items-center justify-center">
            <Layers className="h-3.5 w-3.5 text-[var(--brand-hover)]" />
          </div>
          <span className="font-bold tracking-tight text-[var(--text-primary)] uppercase text-[11px]">
            LOOM <span className="text-[var(--text-muted)] font-normal">{'// v0.1.0'}</span>
          </span>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 bg-[var(--bg-surface)]/70 border border-[var(--border-subtle)] px-2.5 py-1 rounded-full text-[10px] text-[var(--text-secondary)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--success)] animate-pulse" />
            <span className="hidden sm:inline">CONTROL PLANE</span> READY
          </div>
          <div className="hidden sm:flex items-center gap-1.5 bg-[var(--bg-surface)]/70 border border-[var(--border-subtle)] px-2.5 py-1 rounded-full text-[10px] text-[var(--text-muted)]">
            <ShieldCheck className="h-3 w-3 text-[var(--cyan)]" />
            <span>EAL4+ ENCLAVE</span>
          </div>
        </div>
      </header>

      {/* CENTER LOGIN CARD */}
      <div className="relative z-10 my-auto w-full max-w-md mx-auto">
        <div className="p-[1px] rounded-2xl bg-gradient-to-b from-[var(--brand)]/40 via-[var(--border-default)]/60 to-[var(--border-subtle)]/40 shadow-[0_0_60px_-15px_rgba(124,92,255,0.25)]">
          <div className="w-full rounded-2xl bg-[var(--bg-surface)]/95 backdrop-blur-2xl p-7 sm:p-9 space-y-6 relative overflow-hidden">
            {/* Top glowing sheen accent */}
            <div className="absolute top-0 inset-x-0 h-[2px] bg-gradient-to-r from-transparent via-[var(--brand)] to-transparent opacity-80" />

            {/* Brand Header */}
            <div className="flex items-start gap-3.5">
              <div className="relative">
                <div className="h-11 w-11 rounded-xl bg-gradient-to-br from-[var(--brand)] to-[var(--brand-hover)] flex items-center justify-center shadow-lg shadow-[var(--brand)]/30 text-white font-mono font-bold text-base shrink-0">
                  <Layers className="h-5 w-5 text-white" />
                </div>
                <span className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full bg-[var(--success)] border-2 border-[var(--bg-surface)]" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h1 className="text-sm font-bold tracking-tight text-[var(--text-primary)] uppercase font-mono">
                    Loom Dashboard
                  </h1>
                  <span className="status-pill status-pill-idle text-[9px] py-0.5 px-2 font-mono">
                    CONTROL PLANE
                  </span>
                </div>
                <p className="text-xs text-[var(--text-muted)] mt-1 leading-relaxed">
                  Authenticate to access autonomous engineering harness
                </p>
              </div>
            </div>

            {/* Error Message Display */}
            {error && (
              <div
                className="rounded-xl border border-[var(--danger)]/40 bg-[var(--danger)]/10 p-3.5 text-xs text-[var(--danger)] flex items-start gap-2.5 font-mono shadow-sm animate-fadeIn"
                role="alert"
              >
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                <div className="leading-relaxed flex-1 text-[11px] break-words">{error}</div>
              </div>
            )}

            {/* Google Sign-In Option */}
            <div>
              <a
                href="/api/auth/google"
                className="w-full h-11 rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)]/70 hover:bg-[var(--bg-hover)] hover:border-[var(--brand)]/60 text-xs font-mono font-semibold text-[var(--text-primary)] transition-all duration-200 flex items-center justify-center gap-3 px-4 shadow-sm hover:shadow-[0_0_20px_rgba(124,92,255,0.15)] group"
              >
                <svg className="h-4 w-4 shrink-0 transition-transform group-hover:scale-105" viewBox="0 0 24 24">
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
                <ArrowRight className="h-3.5 w-3.5 ml-auto text-[var(--text-muted)] group-hover:text-[var(--text-primary)] group-hover:translate-x-0.5 transition-all opacity-60 group-hover:opacity-100" />
              </a>
            </div>

            {/* Divider */}
            <div className="relative my-4 flex items-center justify-center">
              <div className="w-full border-t border-[var(--border-subtle)]" />
              <span className="absolute bg-[var(--bg-surface)] px-3 text-[10px] font-mono font-bold uppercase tracking-wider text-[var(--text-muted)] border border-[var(--border-subtle)]/70 rounded-full py-0.5">
                or continue with token
              </span>
            </div>

            {/* Token Sign-In Form */}
            <form onSubmit={login} className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-[11px] font-mono font-bold uppercase text-[var(--text-muted)] flex items-center gap-1.5">
                    <Key className="h-3 w-3 text-[var(--brand)]" />
                    <span>Dashboard Token / Root API Key</span>
                  </label>
                </div>
                <div className="relative flex items-center">
                  <div className="absolute left-3.5 text-[var(--text-muted)] pointer-events-none">
                    <Lock className="h-3.5 w-3.5" />
                  </div>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={token}
                    onChange={(event) => setToken(event.target.value)}
                    placeholder="Enter master token or API key"
                    autoComplete="current-password"
                    className="w-full rounded-xl border border-[var(--border-default)] bg-[var(--bg-root)] pl-9 pr-10 py-2.5 text-xs font-mono text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-muted)]/60 focus:border-[var(--brand)] focus:ring-2 focus:ring-[var(--brand)]/20"
                  />
                  {token.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition p-1"
                      title={showPassword ? 'Hide token' : 'Show token'}
                      tabIndex={-1}
                    >
                      {showPassword ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                    </button>
                  )}
                </div>
              </div>

              <button
                type="submit"
                disabled={checking || !token.trim()}
                className="btn-primary w-full h-11 text-xs font-mono font-bold uppercase tracking-wider gap-2 shadow-lg shadow-[var(--brand)]/20 hover:shadow-[var(--brand)]/40 transition-all group"
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
        </div>

        {/* Feature Badges below Card */}
        <div className="mt-6 grid grid-cols-2 gap-2 text-[10px] font-mono text-[var(--text-muted)]">
          <div className="flex items-center gap-2 p-2.5 rounded-xl bg-[var(--bg-surface)]/60 border border-[var(--border-subtle)]/80 backdrop-blur-md">
            <Cpu className="h-3.5 w-3.5 text-[var(--cyan)] shrink-0" />
            <span className="truncate">5-Stage DAG Engine</span>
          </div>
          <div className="flex items-center gap-2 p-2.5 rounded-xl bg-[var(--bg-surface)]/60 border border-[var(--border-subtle)]/80 backdrop-blur-md">
            <ShieldCheck className="h-3.5 w-3.5 text-[var(--success)] shrink-0" />
            <span className="truncate">SHA-256 Hash Audit</span>
          </div>
          <div className="flex items-center gap-2 p-2.5 rounded-xl bg-[var(--bg-surface)]/60 border border-[var(--border-subtle)]/80 backdrop-blur-md">
            <Terminal className="h-3.5 w-3.5 text-[var(--warning)] shrink-0" />
            <span className="truncate">Tier A/B/C Sandboxes</span>
          </div>
          <div className="flex items-center gap-2 p-2.5 rounded-xl bg-[var(--bg-surface)]/60 border border-[var(--border-subtle)]/80 backdrop-blur-md">
            <GitBranch className="h-3.5 w-3.5 text-[var(--brand)] shrink-0" />
            <span className="truncate">Multi-Model Routing</span>
          </div>
        </div>
      </div>

      {/* FOOTER */}
      <footer className="relative z-10 w-full max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2 pt-6 px-2 text-[11px] font-mono text-[var(--text-muted)]">
        <div className="flex items-center gap-2">
          <span>Loom Autonomous Engineering Harness</span>
          <span>•</span>
          <span className="text-[var(--text-secondary)]">Tamper-Evident Runtime</span>
        </div>
        <div>
          <span>Confidential Access Only</span>
        </div>
      </footer>
    </main>
  );
}
