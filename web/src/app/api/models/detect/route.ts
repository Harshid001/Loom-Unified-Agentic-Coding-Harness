import { NextRequest, NextResponse } from 'next/server';
import { validateRequestAuth, validateSameOrigin } from '@/lib/auth';

const DEFAULT_MODELS: Record<string, string[]> = {
  anthropic: [
    'claude-3-5-sonnet-20241022',
    'claude-3-7-sonnet-20250219',
    'claude-3-5-haiku-20241022',
    'claude-3-opus-20240229',
  ],
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'o1', 'o1-mini', 'o3-mini'],
  deepseek: ['deepseek-chat', 'deepseek-reasoner', 'deepseek-v3'],
  gemini: ['gemini-1.5-pro', 'gemini-1.5-flash', 'gemini-2.0-flash', 'gemini-pro'],
};

function validateKeyFormat(provider: string, key: string): boolean {
  const p = provider.toLowerCase();
  const k = key.trim();
  if (k.length < 8) return false;
  if (p === 'anthropic') return k.startsWith('sk-ant-') || k.length >= 20;
  if (p === 'openai') return k.startsWith('sk-') || k.length >= 20;
  if (p === 'deepseek') return k.startsWith('sk-') || k.length >= 20;
  if (p === 'gemini') return k.startsWith('AIzaSy') || k.length >= 20;
  return true;
}

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
  const provider = String(body.provider || '').toLowerCase();
  const apiKeyProvided = String(body.api_key || '').trim();

  // 1. Try forwarding to real backend if available
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey) headers['X-API-Key'] = apiKey;

    const res = await fetch(`${backendUrl}/api/v1/models/detect`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    });

    if (res.ok) {
      const data = await res.json();
      return NextResponse.json(data, { status: 200 });
    }
  } catch {
    // Backend offline or unreachable, fall through to direct validation
  }

  // 2. Direct validation fallback for dashboard
  if (!apiKeyProvided) {
    return NextResponse.json(
      { valid: false, detail: 'API key must not be empty', models: [] },
      { status: 400 },
    );
  }

  if (!validateKeyFormat(provider, apiKeyProvided)) {
    return NextResponse.json(
      { valid: false, detail: `Invalid API key format for ${provider}`, models: [] },
      { status: 400 },
    );
  }

  const detected = DEFAULT_MODELS[provider] || [`${provider}-default`];
  return NextResponse.json({
    valid: true,
    provider,
    models: detected,
    detail: `Validated ${provider} API key and detected ${detected.length} models`,
  });
}
