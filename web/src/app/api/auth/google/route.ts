import { NextRequest, NextResponse } from 'next/server';
import { getAppOrigin, signOAuthState } from '@/lib/auth';

export async function GET(req: NextRequest) {
  const clientId = process.env.GOOGLE_CLIENT_ID?.trim();
  const origin = getAppOrigin(req);

  if (!clientId) {
    if (process.env.NODE_ENV !== 'production') {
      console.error(
        '[Google OAuth] GOOGLE_CLIENT_ID is not set. ' +
          'Set it in your environment (e.g. .env.local or shell export) ' +
          'to enable Google sign-in. Redirecting with error code google_oauth_unconfigured.'
      );
    }
    return NextResponse.redirect(`${origin}/?error=google_oauth_unconfigured`);
  }

  const redirectUri = `${origin}/api/auth/callback/google`;
  const state = signOAuthState({ redirectUri });

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

