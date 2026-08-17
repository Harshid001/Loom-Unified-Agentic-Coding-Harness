import crypto from 'node:crypto';
import { NextRequest, NextResponse } from 'next/server';

export function signOAuthState(): string {
  const secret = process.env.GOOGLE_CLIENT_SECRET?.trim() || process.env.DASHBOARD_SESSION_SECRET?.trim() || 'loom_oauth_state_fallback_secret_2026';
  const payload = Buffer.from(JSON.stringify({ t: Date.now(), n: crypto.randomBytes(16).toString('hex') })).toString('base64url');
  const sig = crypto.createHmac('sha256', secret).update(payload).digest('base64url');
  return `${payload}.${sig}`;
}

export function verifyOAuthState(state: string | null | undefined): boolean {
  if (!state || typeof state !== 'string') return false;
  const parts = state.split('.');
  if (parts.length !== 2) return false;
  const [payload, sig] = parts;
  const secret = process.env.GOOGLE_CLIENT_SECRET?.trim() || process.env.DASHBOARD_SESSION_SECRET?.trim() || 'loom_oauth_state_fallback_secret_2026';
  const expectedSig = crypto.createHmac('sha256', secret).update(payload).digest('base64url');
  if (sig !== expectedSig) return false;
  try {
    const data = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
    const ageMs = Date.now() - Number(data.t);
    return ageMs >= 0 && ageMs < 15 * 60 * 1000; // 15 minutes validity
  } catch {
    return false;
  }
}

function getAppOrigin(req: NextRequest): string {
  const configured = process.env.NEXT_PUBLIC_APP_ORIGIN?.trim();
  if (configured) return configured.replace(/\/+$/, '');
  const host = req.headers.get('x-forwarded-host') || req.headers.get('host') || req.nextUrl.host;
  const proto = req.headers.get('x-forwarded-proto') || req.nextUrl.protocol.replace(/:$/, '') || 'https';
  return `${proto}://${host}`;
}

export async function GET(req: NextRequest) {
  const clientId = process.env.GOOGLE_CLIENT_ID?.trim();
  if (!clientId) {
    const origin = getAppOrigin(req);
    return NextResponse.redirect(`${origin}/?error=google_oauth_unconfigured`);
  }

  const origin = getAppOrigin(req);
  const redirectUri = `${origin}/api/auth/callback/google`;
  const state = signOAuthState();

  const authUrl = new URL('https://accounts.google.com/o/oauth2/v2/auth');
  authUrl.searchParams.set('client_id', clientId);
  authUrl.searchParams.set('redirect_uri', redirectUri);
  authUrl.searchParams.set('response_type', 'code');
  authUrl.searchParams.set('scope', 'openid email profile');
  authUrl.searchParams.set('state', state);
  authUrl.searchParams.set('prompt', 'select_account');
  authUrl.searchParams.set('access_type', 'offline');

  return NextResponse.redirect(authUrl.toString());
}

