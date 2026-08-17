import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { createDashboardSession, validateRequestAuth, DASHBOARD_SESSION_COOKIE } from '../src/lib/auth';

describe('validateRequestAuth', () => {
  const originalEnv = process.env.DASHBOARD_AUTH_TOKEN;

  beforeEach(() => {
    delete process.env.DASHBOARD_AUTH_TOKEN;
  });

  afterEach(() => {
    process.env.DASHBOARD_AUTH_TOKEN = originalEnv;
    vi.unstubAllEnvs();
  });

  it('keeps development fail-open behavior only when no token is configured', () => {
    vi.stubEnv('NODE_ENV', 'development');
    const req = new NextRequest('http://localhost:3000/api/runs');
    expect(validateRequestAuth(req).isAuthorized).toBe(true);
  });

  it('fails closed in production when no dashboard token is configured', () => {
    vi.stubEnv('NODE_ENV', 'production');
    const req = new NextRequest('http://localhost:3000/api/runs');
    const result = validateRequestAuth(req);
    expect(result.isAuthorized).toBe(false);
    expect(result.reason).toContain('DASHBOARD_AUTH_TOKEN');
  });

  it('accepts the secure dashboard session cookie', () => {
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubEnv('DASHBOARD_AUTH_TOKEN', 'secret-token-123');
    const session = createDashboardSession();
    expect(session).not.toBeNull();
    const req = new NextRequest('http://localhost:3000/api/runs', {
      headers: { Cookie: `${DASHBOARD_SESSION_COOKIE}=${session}` },
    });
    expect(validateRequestAuth(req).isAuthorized).toBe(true);
  });

  it('rejects an invalid session cookie', () => {
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubEnv('DASHBOARD_AUTH_TOKEN', 'secret-token-123');
    const req = new NextRequest('http://localhost:3000/api/runs', {
      headers: { Cookie: `${DASHBOARD_SESSION_COOKIE}=wrong-token` },
    });
    const result = validateRequestAuth(req);
    expect(result.isAuthorized).toBe(false);
    expect(result.reason).toContain('Invalid');
  });

  it('accepts valid bearer authorization as a service-to-service compatibility path', () => {
    vi.stubEnv('NODE_ENV', 'production');
    process.env.DASHBOARD_AUTH_TOKEN = 'secret-token-123';
    const req = new NextRequest('http://localhost:3000/api/runs', {
      headers: { Authorization: 'Bearer secret-token-123' },
    });
    expect(validateRequestAuth(req).isAuthorized).toBe(true);
  });
});

describe('Google OAuth & Session Routes', () => {
  it('handles GET /api/auth/session with valid cookie', async () => {
    const { GET: sessionHandler } = await import('../src/app/api/auth/session/route');
    vi.stubEnv('DASHBOARD_AUTH_TOKEN', 'test-auth-token-123');
    const session = createDashboardSession();
    const req = new NextRequest('http://localhost:3000/api/auth/session', {
      headers: { Cookie: `${DASHBOARD_SESSION_COOKIE}=${session}` },
    });
    const res = await sessionHandler(req);
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.authenticated).toBe(true);
  });

  it('handles GET /api/auth/session without auth', async () => {
    const { GET: sessionHandler } = await import('../src/app/api/auth/session/route');
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubEnv('DASHBOARD_AUTH_TOKEN', 'test-auth-token-123');
    const req = new NextRequest('http://localhost:3000/api/auth/session');
    const res = await sessionHandler(req);
    expect(res.status).toBe(401);
  });

  it('redirects to Google accounts on /api/auth/google when configured', async () => {
    const { GET: googleHandler } = await import('../src/app/api/auth/google/route');
    vi.stubEnv('GOOGLE_CLIENT_ID', 'test-google-client-id.apps.googleusercontent.com');
    const req = new NextRequest('http://localhost:3000/api/auth/google');
    const res = await googleHandler(req);
    expect(res.status).toBe(307);
    const location = res.headers.get('location');
    expect(location).toContain('accounts.google.com/o/oauth2/v2/auth');
    expect(location).toContain('client_id=test-google-client-id.apps.googleusercontent.com');
  });

  it('redirects with error on /api/auth/google when unconfigured', async () => {
    const { GET: googleHandler } = await import('../src/app/api/auth/google/route');
    delete process.env.GOOGLE_CLIENT_ID;
    const req = new NextRequest('http://localhost:3000/api/auth/google');
    const res = await googleHandler(req);
    expect(res.status).toBe(307);
    const location = res.headers.get('location');
    expect(location).toContain('error=google_oauth_unconfigured');
  });
});

