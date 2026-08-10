import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { validateRequestAuth } from '../src/lib/auth';

describe('validateRequestAuth', () => {
  const originalEnv = process.env.DASHBOARD_AUTH_TOKEN;

  beforeEach(() => {
    delete process.env.DASHBOARD_AUTH_TOKEN;
  });

  afterEach(() => {
    process.env.DASHBOARD_AUTH_TOKEN = originalEnv;
    vi.unstubAllEnvs();
  });

  it('should allow requests when DASHBOARD_AUTH_TOKEN is not configured in development mode', () => {
    vi.stubEnv('NODE_ENV', 'development');
    const req = new NextRequest('http://localhost:3000/api/runs');
    const result = validateRequestAuth(req);
    expect(result.isAuthorized).toBe(true);
  });

  it('should reject requests when DASHBOARD_AUTH_TOKEN is not configured in production mode', () => {
    vi.stubEnv('NODE_ENV', 'production');
    const req = new NextRequest('http://localhost:3000/api/runs');
    const result = validateRequestAuth(req);
    expect(result.isAuthorized).toBe(false);
    expect(result.reason).toContain('DASHBOARD_AUTH_TOKEN');
  });

  it('should reject requests missing Authorization header when auth token is configured', () => {
    process.env.DASHBOARD_AUTH_TOKEN = 'secret-token-123';
    const req = new NextRequest('http://localhost:3000/api/runs');
    const result = validateRequestAuth(req);
    expect(result.isAuthorized).toBe(false);
    expect(result.reason).toContain('Missing');
  });

  it('should reject invalid authorization tokens', () => {
    process.env.DASHBOARD_AUTH_TOKEN = 'secret-token-123';
    const req = new NextRequest('http://localhost:3000/api/runs', {
      headers: { Authorization: 'Bearer wrong-token' }
    });
    const result = validateRequestAuth(req);
    expect(result.isAuthorized).toBe(false);
    expect(result.reason).toContain('Invalid');
  });

  it('should accept valid authorization tokens', () => {
    process.env.DASHBOARD_AUTH_TOKEN = 'secret-token-123';
    const req = new NextRequest('http://localhost:3000/api/runs', {
      headers: { Authorization: 'Bearer secret-token-123' }
    });
    const result = validateRequestAuth(req);
    expect(result.isAuthorized).toBe(true);
  });
});
