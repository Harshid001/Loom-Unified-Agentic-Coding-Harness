import { NextRequest, NextResponse } from 'next/server';
import {
  DASHBOARD_SESSION_COOKIE,
  SESSION_TTL_SECONDS,
  createDashboardSession,
} from '@/lib/auth';
import { GOOGLE_OAUTH_STATE_COOKIE } from '../route';

function getAppOrigin(req: NextRequest): string {
  const configured = process.env.NEXT_PUBLIC_APP_ORIGIN?.trim();
  if (configured) return configured.replace(/\/+$/, '');
  const host = req.headers.get('x-forwarded-host') || req.headers.get('host') || req.nextUrl.host;
  const proto = req.headers.get('x-forwarded-proto') || req.nextUrl.protocol.replace(/:$/, '') || 'https';
  return `${proto}://${host}`;
}

function isEmailAllowed(email: string): boolean {
  const allowed = process.env.ALLOWED_GOOGLE_EMAILS?.trim();
  if (!allowed) {
    // If no whitelist is specified, any authenticated Google account is allowed
    return true;
  }
  const emailList = allowed.split(',').map((e) => e.trim().toLowerCase()).filter(Boolean);
  if (emailList.length === 0) return true;
  return emailList.includes(email.toLowerCase());
}

export async function GET(req: NextRequest) {
  const origin = getAppOrigin(req);
  const searchParams = req.nextUrl.searchParams;

  const oauthError = searchParams.get('error');
  if (oauthError) {
    return NextResponse.redirect(`${origin}/?error=${encodeURIComponent(oauthError)}`);
  }

  const code = searchParams.get('code');
  const state = searchParams.get('state');
  const storedState = req.cookies.get(GOOGLE_OAUTH_STATE_COOKIE)?.value;

  if (!code || !state || !storedState || state !== storedState) {
    return NextResponse.redirect(`${origin}/?error=invalid_oauth_state`);
  }

  const clientId = process.env.GOOGLE_CLIENT_ID?.trim();
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET?.trim();
  if (!clientId || !clientSecret) {
    return NextResponse.redirect(`${origin}/?error=google_oauth_unconfigured`);
  }

  const redirectUri = `${origin}/api/auth/callback/google`;

  try {
    const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        client_id: clientId,
        client_secret: clientSecret,
        code,
        grant_type: 'authorization_code',
        redirect_uri: redirectUri,
      }),
    });

    if (!tokenRes.ok) {
      const errText = await tokenRes.text();
      console.error('Google token exchange error:', errText);
      return NextResponse.redirect(`${origin}/?error=google_token_exchange_failed`);
    }

    const tokenData = await tokenRes.json();
    const accessToken = tokenData.access_token;

    const userRes = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
      headers: { Authorization: `Bearer ${accessToken}` },
    });

    if (!userRes.ok) {
      return NextResponse.redirect(`${origin}/?error=google_userinfo_failed`);
    }

    const userData = await userRes.json();
    const email = userData.email;
    const verified = userData.email_verified;

    if (!email || !verified) {
      return NextResponse.redirect(`${origin}/?error=unverified_email`);
    }

    if (!isEmailAllowed(email)) {
      return NextResponse.redirect(`${origin}/?error=unauthorized_email&email=${encodeURIComponent(email)}`);
    }

    const session = createDashboardSession();
    if (!session) {
      return NextResponse.redirect(`${origin}/?error=session_creation_failed`);
    }

    const response = NextResponse.redirect(`${origin}/`);
    response.cookies.set({
      name: DASHBOARD_SESSION_COOKIE,
      value: session,
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      path: '/',
      maxAge: SESSION_TTL_SECONDS,
    });
    response.cookies.delete(GOOGLE_OAUTH_STATE_COOKIE);

    return response;
  } catch (err) {
    console.error('OAuth callback exception:', err);
    return NextResponse.redirect(`${origin}/?error=oauth_internal_error`);
  }
}
