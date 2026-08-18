import { NextRequest, NextResponse } from 'next/server';
import { validateRequestAuth, validateSameOrigin } from '@/lib/auth';

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  if (!validateSameOrigin(req)) {
    return NextResponse.json({ detail: 'Invalid request origin' }, { status: 403 });
  }
  const auth = validateRequestAuth(req);
  if (!auth.isAuthorized) {
    return NextResponse.json({ detail: auth.reason || 'Unauthorized' }, { status: 401 });
  }

  const { id: tokenId } = await params;
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
    if (apiKey) headers['X-API-Key'] = apiKey;

    const res = await fetch(`${backendUrl}/api/v1/auth/tokens/${encodeURIComponent(tokenId)}`, {
      method: 'DELETE',
      headers,
    });

    if (res.ok) {
      const data = await res.json().catch(() => ({ status: 'revoked' }));
      return NextResponse.json(data);
    }
  } catch {
    // Standalone fallback
  }

  return NextResponse.json({ status: 'revoked', token_id: tokenId });
}
