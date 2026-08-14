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
