import { NextResponse } from 'next/server';

import { proxyPost } from '@/lib/bff';

// POST /api/retrieve → proxies to the FastAPI /api/v1/retrieve (hybrid/lexical/vector).
export async function POST(request: Request): Promise<NextResponse> {
  const payload = await request.json().catch(() => null);
  if (!payload || typeof payload.query !== 'string' || payload.query.trim() === '') {
    return NextResponse.json({ detail: 'query is required' }, { status: 400 });
  }
  const { status, body } = await proxyPost('/api/v1/retrieve', payload);
  return NextResponse.json(body, { status });
}
