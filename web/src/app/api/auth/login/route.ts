import { createHash, randomBytes } from 'node:crypto';
import { NextRequest, NextResponse } from 'next/server';

import { DASHBOARD_SESSION_COOKIE, isDashboardTokenValid } from '@/lib/auth';

const failures = new Map<string, number[]>();
const WINDOW_MS = 60_000;
const MAX_FAILURES = 10;

function clientKey(req: NextRequest, token: string): string {
  const forwarded = req.headers.get('x-forwarded-for')?.split(',')[0]?.trim() || 'unknown';
  return createHash('sha256').update(`${forwarded}:${token}`).digest('hex');
}

function rateLimited(key: string): boolean {
  const now = Date.now();
  const recent = (failures.get(key) || []).filter(ts => now - ts < WINDOW_MS);
  failures.set(key, recent);
  return recent.length >= MAX_FAILURES;
}

function recordFailure(key: string): void {
  const now = Date.now();
  const recent = (failures.get(key) || []).filter(ts => now - ts < WINDOW_MS);
  recent.push(now);
  failures.set(key, recent);
}

export async function POST(req: NextRequest) {
  const origin = req.headers.get('origin');
  const configuredOrigin = process.env.NEXT_PUBLIC_APP_ORIGIN;
  if (configuredOrigin && origin && origin !== configuredOrigin) {
    return NextResponse.json({ detail: 'Invalid request origin' }, { status: 403 });
  }

  const token = (await req.json().catch(() => ({}))).token;
  if (typeof token !== 'string') {
    return NextResponse.json({ detail: 'Invalid dashboard credentials' }, { status: 401 });
  }

  const key = clientKey(req, token);
  if (rateLimited(key)) {
    return NextResponse.json({ detail: 'Too many failed login attempts' }, { status: 429 });
  }

  if (!isDashboardTokenValid(token)) {
    recordFailure(key);
    return NextResponse.json({ detail: 'Invalid dashboard credentials' }, { status: 401 });
  }

  const sessionId = randomBytes(32).toString('hex');
  const response = NextResponse.json({ authenticated: true });
  response.cookies.set({
    name: DASHBOARD_SESSION_COOKIE,
    value: sessionId,
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'strict',
    path: '/',
    maxAge: 60 * 60 * 8,
  });
  return response;
}
