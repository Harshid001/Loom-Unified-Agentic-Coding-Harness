import { NextRequest, NextResponse } from 'next/server';
import { signOAuthState } from '@/lib/auth';

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

