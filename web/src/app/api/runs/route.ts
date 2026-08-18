import { NextRequest, NextResponse } from 'next/server';
import { validateRequestAuth } from '@/lib/auth';
import { globalRunsStore } from '@/lib/runs_store';

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
    if (apiKey) {
      headers['X-API-Key'] = apiKey;
    }
    const res = await fetch(`${backendUrl}/api/v1/runs`, { headers, cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data) && data.length > 0) {
        return NextResponse.json(data);
      }
    }
  } catch {
    // Backend offline or unreachable
  }

  // Return stored runs
  const runs = Array.from(globalRunsStore.values()).map(r => ({
    id: r.id,
    issue: r.issue,
    status: r.status,
    cost: r.cost,
    created_at: r.created_at,
  }));
  return NextResponse.json(runs);
}
