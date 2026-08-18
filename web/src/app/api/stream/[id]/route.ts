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
  const apiKey = (
    req.headers.get('x-api-key') ||
    req.nextUrl.searchParams.get('api_key') ||
    req.headers.get('authorization')?.replace(/^Bearer\s+/i, '').trim() ||
    process.env.API_KEY ||
    process.env.LOOM_API_KEY ||
    ''
  );

  const headers: Record<string, string> = {
    Accept: 'text/event-stream',
  };
  if (apiKey) headers['X-API-Key'] = apiKey;

  // 1. Forward directly to real Python backend SSE stream
  try {
    const backendRes = await fetch(`${backendUrl}/api/v1/stream/${encodeURIComponent(runId)}`, {
      headers,
    });

    if (backendRes.ok && backendRes.body) {
      return new Response(backendRes.body, {
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache, no-transform',
          Connection: 'keep-alive',
        },
      });
    }
  } catch {
    // Backend offline / unreachable
  }

  // 2. If backend is unreachable, emit honest failure notification (do NOT simulate fake success)
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      function sendEvent(type: string, step_name: string, data: any) {
        const payload = JSON.stringify({
          type,
          step_name,
          timestamp: new Date().toISOString(),
          data,
        });
        controller.enqueue(encoder.encode(`data: ${payload}\n\n`));
      }

      sendEvent('log_entry', 'system', {
        level: 'error',
        message: `Loom harness backend is unreachable at ${backendUrl}. Execution cannot proceed without a running backend.`,
      });
      sendEvent('status_change', 'system', {
        status: 'failed',
        error: `Backend unreachable at ${backendUrl}. Real execution requires the Python backend.`,
      });

      try {
        controller.close();
      } catch {}
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
    },
  });
}
