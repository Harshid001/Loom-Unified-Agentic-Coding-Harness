import { NextRequest } from 'next/server';
import crypto from 'crypto';

export const DASHBOARD_SESSION_COOKIE = 'loom_dashboard_session';
const SESSION_TTL_SECONDS = 60 * 60 * 8;

function safeCompare(a: string, b: string): boolean {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

function configuredToken(): string | null {
  const token = process.env.DASHBOARD_AUTH_TOKEN?.trim();
  return token || null;
}

function sessionSecret(): string | null {
  return process.env.DASHBOARD_SESSION_SECRET?.trim() || configuredToken();
}

function signSession(sessionId: string, issuedAt: number): string | null {
  const secret = sessionSecret();
  if (!secret) return null;
  const payload = `${sessionId}.${issuedAt}`;
  return crypto.createHmac('sha256', secret).update(payload).digest('hex');
}

export function createDashboardSession(): string | null {
  const sessionId = crypto.randomBytes(32).toString('base64url');
  const issuedAt = Math.floor(Date.now() / 1000);
  const signature = signSession(sessionId, issuedAt);
  return signature ? `${sessionId}.${issuedAt}.${signature}` : null;
}

function validateDashboardSession(value: string): boolean {
  const parts = value.split('.');
  if (parts.length !== 3) return false;
  const [sessionId, issuedAtRaw, signature] = parts;
  const issuedAt = Number(issuedAtRaw);
  if (!sessionId || !Number.isSafeInteger(issuedAt) || issuedAt <= 0) return false;
  if (Math.floor(Date.now() / 1000) - issuedAt > SESSION_TTL_SECONDS) return false;
  const expected = signSession(sessionId, issuedAt);
  return Boolean(expected && safeCompare(signature, expected));
}

export function validateSameOrigin(req: NextRequest): boolean {
  const origin = req.headers.get('origin');
  if (!origin) return true;
  const configured = process.env.NEXT_PUBLIC_APP_ORIGIN?.trim();
  if (configured) return origin === configured;
  return origin === `${req.nextUrl.protocol}//${req.nextUrl.host}`;
}

export function validateRequestAuth(req: NextRequest): { isAuthorized: boolean; reason?: string } {
  const authToken = configuredToken();
  const isDev = process.env.NODE_ENV === 'development';

  if (!authToken) {
    if (isDev) return { isAuthorized: true };
    return { isAuthorized: false, reason: 'DASHBOARD_AUTH_TOKEN environment variable is not configured' };
  }

  const cookieToken = req.cookies.get(DASHBOARD_SESSION_COOKIE)?.value;
  if (cookieToken && validateDashboardSession(cookieToken)) {
    return { isAuthorized: true };
  }

  const authHeader = req.headers.get('Authorization') || req.headers.get('x-dashboard-auth');
  const headerToken = authHeader?.replace(/^Bearer\s+/i, '').trim();
  if (!headerToken) {
    return { isAuthorized: false, reason: 'Authentication required' };
  }

  if (!safeCompare(headerToken, authToken)) {
    return { isAuthorized: false, reason: 'Invalid authorization token' };
  }

  return { isAuthorized: true };
}

export function isDashboardTokenValid(token: string): boolean {
  const authToken = configuredToken();
  return Boolean(authToken && safeCompare(token.trim(), authToken));
}

export { SESSION_TTL_SECONDS };
