import { NextRequest, NextResponse } from 'next/server';
import {
  DASHBOARD_SESSION_COOKIE,
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
    return NextResponse.json({ authenticated: true });
  }

  return NextResponse.json({ authenticated: false }, { status: 401 });
}
