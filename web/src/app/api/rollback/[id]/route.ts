import { NextRequest, NextResponse } from 'next/server';
import { validateRequestAuth } from '@/lib/auth';

export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const auth = validateRequestAuth(req);
  if (!auth.isAuthorized) {
    return NextResponse.json({ detail: auth.reason || 'Unauthorized' }, { status: 401 });
  }

  const backendUrl = process.env.LOOM_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
  const apiKey = process.env.API_KEY || process.env.LOOM_API_KEY || '';
  const runId = params.id;

  try {
    const headers: Record<string, string> = {};
    if (apiKey) {
      headers['X-API-Key'] = apiKey;
    }

    const res = await fetch(`${backendUrl}/api/v1/rollback/${runId}`, {
      method: 'POST',
      headers
    });

    const data = await res.json().catch(() => ({ detail: 'Invalid response from server' }));
    if (!res.ok) {
      return NextResponse.json(data, { status: res.status });
    }
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ detail: err.message || 'Rollback request failed' }, { status: 500 });
  }
}
