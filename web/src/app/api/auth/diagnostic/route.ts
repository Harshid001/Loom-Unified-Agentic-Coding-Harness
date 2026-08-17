import { NextRequest, NextResponse } from 'next/server';
import { validateRequestAuth } from '@/lib/auth';

export async function GET(req: NextRequest) {
  const auth = validateRequestAuth(req);
  if (!auth.isAuthorized) {
    return NextResponse.json({ detail: auth.reason || 'Unauthorized' }, { status: 401 });
  }

  const vars = {
    GOOGLE_CLIENT_ID: process.env.GOOGLE_CLIENT_ID ? 'configured' : 'missing',
    GOOGLE_CLIENT_SECRET: process.env.GOOGLE_CLIENT_SECRET ? 'configured' : 'missing',
    ALLOWED_GOOGLE_EMAILS: process.env.ALLOWED_GOOGLE_EMAILS ? 'configured' : 'not configured',
    DASHBOARD_SESSION_SECRET: process.env.DASHBOARD_SESSION_SECRET ? 'configured' : 'missing',
    NODE_ENV: process.env.NODE_ENV,
    NEXT_PUBLIC_APP_ORIGIN: process.env.NEXT_PUBLIC_APP_ORIGIN ? 'configured' : 'dynamic',
  };
  return NextResponse.json(vars);
}