import { NextRequest, NextResponse } from 'next/server';
import { validateRequestAuth } from '@/lib/auth';

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const auth = validateRequestAuth(req);
  if (!auth.isAuthorized) {
    return NextResponse.json({ detail: auth.reason || 'Unauthorized' }, { status: 401 });
  }

  const { id: runId } = await params;
  if (!runId) {
    return NextResponse.json({ detail: 'Run ID is required' }, { status: 400 });
  }

  const backendUrl = process.env.LOOM_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
  const apiKey = process.env.API_KEY || process.env.LOOM_API_KEY || '';

  const headers: Record<string, string> = {
    Accept: 'text/event-stream',
  };
  if (apiKey) headers['X-API-Key'] = apiKey;

  try {
    const backendRes = await fetch(`${backendUrl}/api/v1/stream/${encodeURIComponent(runId)}`, {
      headers,
    });

    if (!backendRes.ok || !backendRes.body) {
      const errorText = await backendRes.text().catch(() => '');
      return NextResponse.json(
        { detail: errorText || `Backend stream error (${backendRes.status})` },
        { status: backendRes.status }
      );
    }

    return new Response(backendRes.body, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache, no-transform',
        Connection: 'keep-alive',
      },
    });
  } catch (err: unknown) {
    return NextResponse.json(
      { detail: err instanceof Error ? err.message : 'Failed to connect to backend event stream' },
      { status: 500 }
    );
  }
}
