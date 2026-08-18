import { NextRequest, NextResponse } from 'next/server';
import { validateRequestAuth, validateSameOrigin } from '@/lib/auth';

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

  // Proxy directly to real Loom Python backend
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey) headers['X-API-Key'] = apiKey;

    const res = await fetch(`${backendUrl}/api/v1/run`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    });

    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      return NextResponse.json(data, { status: res.status });
    }

    const detailMsg = data.detail || `Loom backend error (${res.status})`;
    return NextResponse.json(
      { detail: detailMsg, code: data.code || `BACKEND_ERROR_${res.status}` },
      { status: res.status }
    );
  } catch (err: any) {
    // Standalone mode explicitly rejects execution rather than fabricating fake verification
    return NextResponse.json(
      {
        detail: `Loom backend is unreachable at ${backendUrl}. Pipeline DAG execution, AST parsing, and gVisor sandbox verification require a running Loom harness backend. Start the backend with: uvicorn loom.api.server:app --port 8000`,
        backend_url: backendUrl,
        code: 'BACKEND_UNREACHABLE',
      },
      { status: 503 }
    );
  }
}
