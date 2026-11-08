import { NextResponse } from 'next/server';

import { proxyDelete, proxyGet, proxyPut } from '@/lib/bff';

interface Context {
  params: Promise<{ tenantId: string }>;
}

export async function GET(_request: Request, context: Context): Promise<NextResponse> {
  const { tenantId } = await context.params;
  const { status, body } = await proxyGet(`/api/v1/platform/organizations/${tenantId}`);
  return NextResponse.json(body, { status });
}

export async function PUT(request: Request, context: Context): Promise<NextResponse> {
  const { tenantId } = await context.params;
  const payload = await request.json().catch(() => null);
  if (!payload) return NextResponse.json({ detail: 'invalid payload' }, { status: 400 });
  const { status, body } = await proxyPut(`/api/v1/platform/organizations/${tenantId}`, payload);
  return NextResponse.json(body, { status });
}

export async function DELETE(request: Request, context: Context): Promise<NextResponse> {
  const { tenantId } = await context.params;
  const expectedName = new URL(request.url).searchParams.get('expected_name') ?? '';
  const query = new URLSearchParams({ confirm: 'true', expected_name: expectedName });
  const { status, body } = await proxyDelete(
    `/api/v1/platform/organizations/${tenantId}?${query.toString()}`,
  );
  return body === null ? new NextResponse(null, { status }) : NextResponse.json(body, { status });
}
