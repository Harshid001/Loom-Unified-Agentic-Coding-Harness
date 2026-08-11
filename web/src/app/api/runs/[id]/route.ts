import { NextRequest, NextResponse } from 'next/server';
import { validateRequestAuth } from '@/lib/auth';

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const auth = validateRequestAuth(req);
  if (!auth.isAuthorized) {
    return NextResponse.json({ detail: auth.reason || 'Unauthorized' }, { status: 401 });
  }

  const backendUrl = process.env.LOOM_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
  const apiKey = process.env.API_KEY || process.env.LOOM_API_KEY || '';
  const { id: runId } = await params;

  try {
    const headers: Record<string, string> = {};
    if (apiKey) {
      headers['X-API-Key'] = apiKey;
    }
    const res = await fetch(`${backendUrl}/api/v1/runs/${runId}`, { headers, cache: 'no-store' });
    if (!res.ok) {
      return NextResponse.json({ detail: `Run not found` }, { status: res.status });
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ detail: err.message || 'Failed to fetch run details' }, { status: 500 });
  }
}
