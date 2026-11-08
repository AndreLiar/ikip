import { NextResponse } from 'next/server';

import { proxyGet, proxyPost } from '@/lib/bff';

export async function GET(): Promise<NextResponse> {
  const { status, body } = await proxyGet('/api/v1/admin/users');
  return NextResponse.json(body, { status });
}

export async function POST(request: Request): Promise<NextResponse> {
  const payload = await request.json().catch(() => null);
  if (!payload) return NextResponse.json({ detail: 'invalid payload' }, { status: 400 });
  const { status, body } = await proxyPost('/api/v1/admin/users', payload);
  return NextResponse.json(body, { status });
}
