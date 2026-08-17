import { NextRequest, NextResponse } from 'next/server';
import {
  DASHBOARD_SESSION_COOKIE,
  SESSION_TTL_SECONDS,
  createDashboardSession,
  getAppOrigin,
  verifyOAuthState,
} from '@/lib/auth';

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
    const errorDescription = searchParams.get('error_description') || '';
    const params = new URLSearchParams({
      error: oauthError,
      ...(errorDescription ? { detail: errorDescription } : {}),
    });
    return NextResponse.redirect(`${origin}/?${params.toString()}`);
  }

  const code = searchParams.get('code');
  const state = searchParams.get('state');

  if (!code || !state) {
    return NextResponse.redirect(`${origin}/?error=missing_oauth_parameters`);
  }

  const stateCheck = verifyOAuthState(state);
  if (!stateCheck.valid) {
    return NextResponse.redirect(`${origin}/?error=invalid_oauth_state`);
  }

  const clientId = process.env.GOOGLE_CLIENT_ID?.trim();
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET?.trim();
  if (!clientId || !clientSecret) {
    return NextResponse.redirect(`${origin}/?error=google_oauth_unconfigured`);
  }

  // Use the exact redirect URI signed into the state token, fallback to current origin
  const redirectUri = stateCheck.redirectUri || `${origin}/api/auth/callback/google`;

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
      let errorReason = 'google_token_exchange_failed';
      let errorDetail = '';
      try {
        const errJson = await tokenRes.json();
        errorReason = errJson.error || errorReason;
        errorDetail = errJson.error_description || '';
      } catch {
        const errText = await tokenRes.text().catch(() => '');
        errorDetail = errText.slice(0, 250);
      }

      console.error('Google token exchange error:', {
        status: tokenRes.status,
        error: errorReason,
        detail: errorDetail,
        redirectUri,
        clientIdPreview: clientId ? `${clientId.slice(0, 12)}...` : 'missing',
      });

      const params = new URLSearchParams({
        error: errorReason,
        ...(errorDetail ? { detail: errorDetail } : {}),
      });
      return NextResponse.redirect(`${origin}/?${params.toString()}`);
    }

    const tokenData = await tokenRes.json();
    const accessToken = tokenData.access_token;

    if (!accessToken) {
      return NextResponse.redirect(`${origin}/?error=google_token_missing`);
    }

    const userRes = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
      headers: { Authorization: `Bearer ${accessToken}` },
    });

    if (!userRes.ok) {
      const errText = await userRes.text().catch(() => '');
      console.error('Google userinfo fetch error:', errText);
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

    return response;
  } catch (err) {
    console.error('OAuth callback exception:', err);
    return NextResponse.redirect(`${origin}/?error=oauth_internal_error`);
  }
}
