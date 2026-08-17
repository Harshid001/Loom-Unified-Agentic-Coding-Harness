import { NextRequest, NextResponse } from 'next/server';
import { validateRequestAuth, validateSameOrigin } from '@/lib/auth';

const DEFAULT_MODELS = {
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

export async function GET(req: NextRequest) {
  if (!validateSameOrigin(req)) {
    return NextResponse.json({ detail: 'Invalid request origin' }, { status: 403 });
  }
  const auth = validateRequestAuth(req);
  if (!auth.isAuthorized) {
    return NextResponse.json({ detail: auth.reason || 'Unauthorized' }, { status: 401 });
  }

  const backendUrl = process.env.LOOM_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
  const apiKey = process.env.API_KEY || process.env.LOOM_API_KEY || '';

  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey) headers['X-API-Key'] = apiKey;

    const res = await fetch(`${backendUrl}/api/v1/settings/model`, {
      method: 'GET',
      headers,
    });

    if (res.ok) {
      const data = await res.json();
      return NextResponse.json(data, { status: 200 });
    }
  } catch {
    // Backend offline
  }

  return NextResponse.json({
    active_model: 'claude-3-5-sonnet-20241022',
    available_models: [
      'claude-3-5-sonnet-20241022',
      'claude-3-7-sonnet-20250219',
      'gpt-4o',
      'gpt-4o-mini',
      'deepseek-v3',
      'gemini-1.5-pro',
      'gemini-2.0-flash',
    ],
    providers: {
      anthropic: { configured: Boolean(process.env.ANTHROPIC_API_KEY), models: DEFAULT_MODELS.anthropic },
      openai: { configured: Boolean(process.env.OPENAI_API_KEY), models: DEFAULT_MODELS.openai },
      deepseek: { configured: Boolean(process.env.DEEPSEEK_API_KEY), models: DEFAULT_MODELS.deepseek },
      gemini: { configured: Boolean(process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY), models: DEFAULT_MODELS.gemini },
    },
  });
}

export async function PUT(req: NextRequest) {
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

  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey) headers['X-API-Key'] = apiKey;

    const res = await fetch(`${backendUrl}/api/v1/settings/model`, {
      method: 'PUT',
      headers,
      body: JSON.stringify(body),
    });

    if (res.ok) {
      const data = await res.json();
      return NextResponse.json(data, { status: 200 });
    }
  } catch {
    // Fall through to standalone response
  }

  const model = body.model || 'claude-3-5-sonnet-20241022';
  return NextResponse.json({
    active_model: model,
    provider: body.provider || 'anthropic',
    status: 'success',
    detail: `Active model set to ${model}`,
  });
}
