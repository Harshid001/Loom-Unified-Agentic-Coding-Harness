import { NextRequest, NextResponse } from 'next/server';
import { validateRequestAuth } from '@/lib/auth';

export async function POST(req: NextRequest) {
  const auth = validateRequestAuth(req);
  if (!auth.isAuthorized) {
    return NextResponse.json({ detail: auth.reason || 'Unauthorized' }, { status: 401 });
  }

  const backendUrl = process.env.LOOM_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
  const apiKey = process.env.API_KEY || process.env.LOOM_API_KEY || '';

  try {
    const body = await req.json();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    };
    if (apiKey) {
      headers['X-API-Key'] = apiKey;
    }

    const res = await fetch(`${backendUrl}/api/v1/run`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body)
    });

    const data = await res.json().catch(() => ({ detail: 'Invalid JSON response from server' }));
    if (!res.ok) {
      return NextResponse.json(data, { status: res.status });
    }
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ detail: err.message || 'Server-side API proxy request failed' }, { status: 500 });
  }
}
