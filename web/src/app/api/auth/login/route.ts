import { NextRequest, NextResponse } from 'next/server';

import { DASHBOARD_SESSION_COOKIE, isDashboardTokenValid } from '@/lib/auth';

export async function POST(req: NextRequest) {
  const token = (await req.json().catch(() => ({}))).token;
  if (typeof token !== 'string' || !isDashboardTokenValid(token)) {
    return NextResponse.json({ detail: 'Invalid dashboard credentials' }, { status: 401 });
  }

  const response = NextResponse.json({ authenticated: true });
  response.cookies.set({
    name: DASHBOARD_SESSION_COOKIE,
    value: token,
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'strict',
    path: '/',
    maxAge: 60 * 60 * 8,
  });
  return response;
}
