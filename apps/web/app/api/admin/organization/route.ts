import { NextResponse } from 'next/server';

import { proxyGet, proxyPut } from '@/lib/bff';

export async function GET(): Promise<NextResponse> {
  const { status, body } = await proxyGet('/api/v1/admin/organization');
  return NextResponse.json(body, { status });
}

export async function PUT(request: Request): Promise<NextResponse> {
  const payload = await request.json().catch(() => null);
  if (!payload) return NextResponse.json({ detail: 'invalid payload' }, { status: 400 });
  const { status, body } = await proxyPut('/api/v1/admin/organization', payload);
  return NextResponse.json(body, { status });
}
