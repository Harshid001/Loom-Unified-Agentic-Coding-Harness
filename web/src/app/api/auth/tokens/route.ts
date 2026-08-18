import { NextRequest, NextResponse } from 'next/server';
import { validateRequestAuth, validateSameOrigin } from '@/lib/auth';

export async function GET(req: NextRequest) {
  const auth = validateRequestAuth(req);
  if (!auth.isAuthorized) {
    return NextResponse.json({ detail: auth.reason || 'Unauthorized' }, { status: 401 });
  }

  const backendUrl = process.env.LOOM_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
  const apiKey = (
    req.headers.get('x-api-key') ||
    req.headers.get('authorization')?.replace(/^Bearer\s+/i, '').trim() ||
    process.env.API_KEY ||
    process.env.LOOM_API_KEY ||
    ''
  );

  try {
    const headers: Record<string, string> = {};
    if (apiKey) headers['X-API-Key'] = apiKey;

    const res = await fetch(`${backendUrl}/api/v1/auth/tokens`, { headers, cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      return NextResponse.json(data);
    }
  } catch {
    // Backend offline
  }

  return NextResponse.json([]);
}

export async function POST(req: NextRequest) {
  if (!validateSameOrigin(req)) {
    return NextResponse.json({ detail: 'Invalid request origin' }, { status: 403 });
  }
  const auth = validateRequestAuth(req);
  if (!auth.isAuthorized) {
    return NextResponse.json({ detail: auth.reason || 'Unauthorized' }, { status: 401 });
  }

  const backendUrl = process.env.LOOM_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
  const body = await req.json().catch(() => ({}));
  const apiKey = (
    body.api_key ||
    body.loom_api_key ||
    req.headers.get('x-api-key') ||
    req.headers.get('authorization')?.replace(/^Bearer\s+/i, '').trim() ||
    process.env.API_KEY ||
    process.env.LOOM_API_KEY ||
    ''
  );

  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey) headers['X-API-Key'] = apiKey;

    const res = await fetch(`${backendUrl}/api/v1/auth/tokens`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    });

    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      return NextResponse.json(data, { status: res.status });
    }

    return NextResponse.json({ detail: data.detail || 'Token creation failed' }, { status: res.status });
  } catch {
    // Standalone fallback: generate a mock dev token
    const crypto = await import('crypto');
    const randomHex = crypto.randomBytes(16).toString('hex');
    const mockToken = `loom_${randomHex}`;
    return NextResponse.json({
      id: `tok_${randomHex.slice(0, 8)}`,
      user_id: body.user_id || 'dev_user',
      org_id: body.org_id || 'default',
      label: body.label || 'dashboard_key',
      token: mockToken,
      prefix: mockToken.slice(0, 10),
      active: true,
      created_at: Math.floor(Date.now() / 1000),
    });
  }
}
