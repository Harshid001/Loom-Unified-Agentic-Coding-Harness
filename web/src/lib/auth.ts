import { NextRequest } from 'next/server';
import crypto from 'crypto';

export const DASHBOARD_SESSION_COOKIE = 'loom_dashboard_session';

function safeCompare(a: string, b: string): boolean {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  if (bufA.length !== bufB.length) {
    return false;
  }
  return crypto.timingSafeEqual(bufA, bufB);
}

function configuredToken(): string | null {
  const token = process.env.DASHBOARD_AUTH_TOKEN?.trim();
  return token || null;
}

export function validateRequestAuth(req: NextRequest): { isAuthorized: boolean; reason?: string } {
  const authToken = configuredToken();
  const isDev = process.env.NODE_ENV === 'development';

  if (!authToken) {
    if (isDev) return { isAuthorized: true };
    return { isAuthorized: false, reason: 'DASHBOARD_AUTH_TOKEN environment variable is not configured' };
  }

  const cookieToken = req.cookies.get(DASHBOARD_SESSION_COOKIE)?.value;
  const authHeader = req.headers.get('Authorization') || req.headers.get('x-dashboard-auth');
  const headerToken = authHeader?.replace(/^Bearer\s+/i, '').trim();
  const candidate = cookieToken || headerToken;

  if (!candidate) {
    return { isAuthorized: false, reason: 'Authentication required' };
  }

  if (!safeCompare(candidate, authToken)) {
    return { isAuthorized: false, reason: 'Invalid authorization token' };
  }

  return { isAuthorized: true };
}

export function isDashboardTokenValid(token: string): boolean {
  const authToken = configuredToken();
  return Boolean(authToken && safeCompare(token.trim(), authToken));
}
