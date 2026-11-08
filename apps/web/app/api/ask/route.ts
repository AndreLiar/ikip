import { NextResponse } from 'next/server';

import { proxyPost } from '@/lib/bff';

// POST /api/ask → proxies to the FastAPI /api/v1/ask (grounded answer, Story 3.5/4.4).
export async function POST(request: Request): Promise<NextResponse> {
  const payload = await request.json().catch(() => null);
  if (!payload || typeof payload.query !== 'string' || payload.query.trim() === '') {
    return NextResponse.json({ detail: 'query is required' }, { status: 400 });
  }
  const { status, body } = await proxyPost('/api/v1/ask', payload);
  return NextResponse.json(body, { status });
}
