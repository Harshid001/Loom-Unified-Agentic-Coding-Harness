import { NextRequest } from 'next/server';

/**
 * Validates request authorization header against DASHBOARD_AUTH_TOKEN environment variable (or default).
 */
export function validateRequestAuth(req: NextRequest): { isAuthorized: boolean; reason?: string } {
  const authToken = process.env.DASHBOARD_AUTH_TOKEN;
  const isDev = process.env.NODE_ENV === 'development';

  // PRD-002: Fail closed in non-development mode if DASHBOARD_AUTH_TOKEN is unset
  if (!authToken) {
    if (isDev) {
      return { isAuthorized: true };
    }
    return { isAuthorized: false, reason: 'DASHBOARD_AUTH_TOKEN environment variable is not configured' };
  }

  const authHeader = req.headers.get('Authorization') || req.headers.get('x-dashboard-auth');
  if (!authHeader) {
    return { isAuthorized: false, reason: 'Missing Authorization header' };
  }

  const token = authHeader.replace(/^Bearer\s+/i, '').trim();
  if (token !== authToken) {
    return { isAuthorized: false, reason: 'Invalid authorization token' };
  }

  return { isAuthorized: true };
}
