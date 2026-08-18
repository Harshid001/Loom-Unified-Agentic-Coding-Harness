import { NextRequest, NextResponse } from 'next/server';
import {
  DASHBOARD_SESSION_COOKIE,
  SESSION_TTL_SECONDS,
  createDashboardSession,
  validateDashboardSession,
  validateRequestAuth,
} from '@/lib/auth';

export async function GET(req: NextRequest) {
  const cookieToken = req.cookies.get(DASHBOARD_SESSION_COOKIE)?.value;
  if (cookieToken && validateDashboardSession(cookieToken)) {
    return NextResponse.json({ authenticated: true });
  }

  const authCheck = validateRequestAuth(req);
  if (authCheck.isAuthorized) {
    const session = createDashboardSession();
    const res = NextResponse.json({ authenticated: true });
    if (session) {
      res.cookies.set({
        name: DASHBOARD_SESSION_COOKIE,
        value: session,
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax',
        path: '/',
        maxAge: SESSION_TTL_SECONDS,
      });
    }
    return res;
  }

  // Seamless local & development mode authentication
  const isDev = process.env.NODE_ENV === 'development' || !process.env.DASHBOARD_AUTH_TOKEN;
  if (isDev) {
    const session = createDashboardSession();
    const res = NextResponse.json({ authenticated: true, auto_authenticated: true });
    if (session) {
      res.cookies.set({
        name: DASHBOARD_SESSION_COOKIE,
        value: session,
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax',
        path: '/',
        maxAge: SESSION_TTL_SECONDS,
      });
    }
    return res;
  }

  return NextResponse.json({ authenticated: false });
}

