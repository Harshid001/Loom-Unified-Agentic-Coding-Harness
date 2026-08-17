import { NextRequest, NextResponse } from 'next/server';
import { validateRequestAuth } from '@/lib/auth';
import { globalRunsStore } from '@/lib/runs_store';

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
    if (res.ok) {
      const data = await res.json();
      return NextResponse.json(data);
    }
  } catch {
    // Backend offline or unreachable
  }

  const stored = globalRunsStore.get(runId);
  if (stored) {
    return NextResponse.json({
      checkpoint: stored.checkpoint,
      trace_events: stored.trace_events,
    });
  }

  return NextResponse.json({ detail: `Run not found` }, { status: 404 });
}
