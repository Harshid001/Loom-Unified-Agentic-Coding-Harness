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

// Ephemeral secret generated once per runtime instance if no secret is configured in environment
const ephemeralProcessSecret = crypto.randomBytes(32).toString('hex');

function sessionSecret(): string {
  return (
    process.env.DASHBOARD_SESSION_SECRET?.trim() ||
    configuredToken() ||
    process.env.API_KEY?.trim() ||
    process.env.LOOM_API_KEY?.trim() ||
    process.env.GOOGLE_CLIENT_SECRET?.trim() ||
    ephemeralProcessSecret
  );
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

export function validateDashboardSession(value: string): boolean {
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
  const appOrigin = getAppOrigin(req);
  if (origin === appOrigin) return true;
  const cleanOrigin = origin.replace(/^https?:\/\//, '').replace(/\/+$/, '');
  const cleanAppOrigin = appOrigin.replace(/^https?:\/\//, '').replace(/\/+$/, '');
  return cleanOrigin === cleanAppOrigin;
}

export function validateRequestAuth(req: NextRequest): { isAuthorized: boolean; reason?: string } {
  // 1. Check session cookie first (used by Google OAuth & web dashboard sessions)
  const cookieToken = req.cookies.get(DASHBOARD_SESSION_COOKIE)?.value;
  if (cookieToken) {
    if (validateDashboardSession(cookieToken)) {
      return { isAuthorized: true };
    }
    return { isAuthorized: false, reason: 'Invalid dashboard session cookie' };
  }

  // 2. Check Bearer / custom header tokens (used for API / CLI callers)
  const authHeader = req.headers.get('Authorization') || req.headers.get('x-dashboard-auth');
  const headerToken = authHeader?.replace(/^Bearer\s+/i, '').trim();
  const authToken = configuredToken();

  if (headerToken) {
    if (authToken && safeCompare(headerToken, authToken)) {
      return { isAuthorized: true };
    }
    const apiKey = process.env.API_KEY?.trim() || process.env.LOOM_API_KEY?.trim();
    if (apiKey && safeCompare(headerToken, apiKey)) {
      return { isAuthorized: true };
    }
    return { isAuthorized: false, reason: 'Invalid authorization token' };
  }

  // 3. Fallback for development mode when no token is configured
  const isDev = process.env.NODE_ENV === 'development';
  if (!authToken && isDev) {
    return { isAuthorized: true };
  }

  if (!authToken) {
    return { isAuthorized: false, reason: 'DASHBOARD_AUTH_TOKEN environment variable is not configured' };
  }

  return { isAuthorized: false, reason: 'Authentication required' };
}

export function isDashboardTokenValid(token: string): boolean {
  const authToken = configuredToken();
  if (authToken && safeCompare(token.trim(), authToken)) {
    return true;
  }
  const apiKey = process.env.API_KEY?.trim() || process.env.LOOM_API_KEY?.trim();
  if (apiKey && safeCompare(token.trim(), apiKey)) {
    return true;
  }
  return false;
}

export async function isDashboardTokenValidAsync(token: string): Promise<boolean> {
  if (isDashboardTokenValid(token)) {
    return true;
  }

  const backendUrl = process.env.LOOM_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
  const cleanToken = token.trim();

  try {
    const res = await fetch(`${backendUrl}/api/v1/auth/tokens`, {
      method: 'GET',
      headers: {
        'X-API-Key': cleanToken,
      },
    });
    if (res.ok) {
      return true;
    }
  } catch {
    // Continue to fallback
  }

  try {
    const res = await fetch(`${backendUrl}/api/settings/model`, {
      method: 'GET',
      headers: {
        'X-API-Key': cleanToken,
      },
    });
    if (res.ok) {
      return true;
    }
  } catch {
    // Backend unreachable
  }

  return false;
}

export function getAppOrigin(req: NextRequest): string {
  const configured = process.env.NEXT_PUBLIC_APP_ORIGIN?.trim();
  if (configured) return configured.replace(/\/+$/, '');

  const rawHost = req.headers.get('x-forwarded-host') || req.headers.get('host') || req.nextUrl.host;
  const host = (rawHost || '').split(',')[0].trim();

  const rawProto = req.headers.get('x-forwarded-proto') || req.nextUrl.protocol.replace(/:$/, '') || 'https';
  const proto = (rawProto || '').split(',')[0].trim() || 'https';

  return `${proto}://${host}`;
}

export function signOAuthState(data?: { redirectUri?: string }): string {
  const secret = sessionSecret();
  const payloadObj = {
    t: Date.now(),
    n: crypto.randomBytes(16).toString('hex'),
    ...(data?.redirectUri ? { r: data.redirectUri } : {}),
  };
  const payload = Buffer.from(JSON.stringify(payloadObj)).toString('base64url');
  const sig = crypto.createHmac('sha256', secret).update(payload).digest('base64url');
  return `${payload}.${sig}`;
}

export function verifyOAuthState(state: string | null | undefined): { valid: boolean; redirectUri?: string } {
  if (!state || typeof state !== 'string') return { valid: false };
  const parts = state.split('.');
  if (parts.length !== 2) return { valid: false };
  const [payload, sig] = parts;
  const secret = sessionSecret();
  const expectedSig = crypto.createHmac('sha256', secret).update(payload).digest('base64url');
  if (sig !== expectedSig) return { valid: false };
  try {
    const data = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
    const ageMs = Date.now() - Number(data.t);
    const valid = ageMs >= 0 && ageMs < 15 * 60 * 1000; // 15 minutes validity
    return { valid, redirectUri: typeof data.r === 'string' ? data.r : undefined };
  } catch {
    return { valid: false };
  }
}

export { SESSION_TTL_SECONDS };
