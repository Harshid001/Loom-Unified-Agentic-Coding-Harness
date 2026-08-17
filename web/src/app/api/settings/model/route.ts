import { NextRequest, NextResponse } from 'next/server';
import { validateRequestAuth, validateSameOrigin } from '@/lib/auth';

export async function GET(req: NextRequest) {
  if (!validateSameOrigin(req)) {
    return NextResponse.json({ detail: 'Invalid request origin' }, { status: 403 });
  }
  const auth = validateRequestAuth(req);
  if (!auth.isAuthorized) {
    return NextResponse.json({ detail: auth.reason || 'Unauthorized' }, { status: 401 });
  }

  const backendUrl = process.env.LOOM_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
  const apiKey = process.env.API_KEY || process.env.LOOM_API_KEY || '';

  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey) headers['X-API-Key'] = apiKey;

    const res = await fetch(`${backendUrl}/api/v1/settings/model`, {
      method: 'GET',
      headers,
    });

    const data = await res.json().catch(() => ({ detail: 'Invalid JSON response from server' }));
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    return NextResponse.json(
      { detail: err instanceof Error ? err.message : 'Model settings get proxy request failed' },
      { status: 500 },
    );
  }
}

export async function PUT(req: NextRequest) {
  if (!validateSameOrigin(req)) {
    return NextResponse.json({ detail: 'Invalid request origin' }, { status: 403 });
  }
  const auth = validateRequestAuth(req);
  if (!auth.isAuthorized) {
    return NextResponse.json({ detail: auth.reason || 'Unauthorized' }, { status: 401 });
  }

  const backendUrl = process.env.LOOM_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
  const apiKey = process.env.API_KEY || process.env.LOOM_API_KEY || '';

  try {
    const body = await req.json();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey) headers['X-API-Key'] = apiKey;

    const res = await fetch(`${backendUrl}/api/v1/settings/model`, {
      method: 'PUT',
      headers,
      body: JSON.stringify(body),
    });

    const data = await res.json().catch(() => ({ detail: 'Invalid JSON response from server' }));
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    return NextResponse.json(
      { detail: err instanceof Error ? err.message : 'Model settings update proxy request failed' },
      { status: 500 },
    );
  }
}
