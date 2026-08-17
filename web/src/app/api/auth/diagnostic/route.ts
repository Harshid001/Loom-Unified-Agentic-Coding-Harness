import { NextResponse } from 'next/server';

export async function GET() {
  const vars = {
    GOOGLE_CLIENT_ID: process.env.GOOGLE_CLIENT_ID ? 'set' : 'missing',
    GOOGLE_CLIENT_SECRET: process.env.GOOGLE_CLIENT_SECRET ? 'set' : 'missing',
    ALLOWED_GOOGLE_EMAILS: process.env.ALLOWED_GOOGLE_EMAILS || 'not set',
    DASHBOARD_SESSION_SECRET: process.env.DASHBOARD_SESSION_SECRET ? 'set' : 'missing',
    NODE_ENV: process.env.NODE_ENV,
    NEXT_PUBLIC_APP_ORIGIN: process.env.NEXT_PUBLIC_APP_ORIGIN || 'not set',
  };
  return NextResponse.json(vars);
}