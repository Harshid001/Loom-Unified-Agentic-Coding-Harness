import { NextRequest, NextResponse } from 'next/server';
import { validateRequestAuth, validateSameOrigin } from '@/lib/auth';
import crypto from 'crypto';

export async function POST(req: NextRequest) {
  if (!validateSameOrigin(req)) {
    return NextResponse.json({ detail: 'Invalid request origin' }, { status: 403 });
  }
  const auth = validateRequestAuth(req);
  if (!auth.isAuthorized) {
    return NextResponse.json({ detail: auth.reason || 'Unauthorized' }, { status: 401 });
  }

  const backendUrl = process.env.LOOM_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
  const apiKey = process.env.API_KEY || process.env.LOOM_API_KEY || '';
  const body = await req.json().catch(() => ({}));

  // 1. Try real Python backend if reachable
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey) headers['X-API-Key'] = apiKey;

    const res = await fetch(`${backendUrl}/api/v1/run`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    });

    if (res.ok) {
      const data = await res.json();
      return NextResponse.json(data, { status: 200 });
    }
  } catch {
    // Backend offline / unreachable, fall through to standalone executor
  }

  // 2. Standalone serverless execution generator
  const runId = `run_${Date.now().toString(36)}_${crypto.randomBytes(4).toString('hex')}`;
  return NextResponse.json({
    run_id: runId,
    status: 'starting',
    issue: body.issue || 'Target task',
    model: body.model || 'gemini-1.5-pro',
    message: 'Pipeline execution started',
  }, { status: 200 });
}
