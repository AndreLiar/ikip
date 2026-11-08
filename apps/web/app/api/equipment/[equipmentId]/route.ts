import { NextResponse } from 'next/server';

import { proxyDelete, proxyPut } from '@/lib/bff';

type Context = { params: Promise<{ equipmentId: string }> };

export async function PUT(request: Request, context: Context): Promise<NextResponse> {
  const { equipmentId } = await context.params;
  const payload = await request.json().catch(() => null);
  if (!payload) return NextResponse.json({ detail: 'invalid payload' }, { status: 400 });
  const { status, body } = await proxyPut(
    `/api/v1/equipment/${encodeURIComponent(equipmentId)}`,
    payload,
  );
  return body === null ? new NextResponse(null, { status }) : NextResponse.json(body, { status });
}

export async function DELETE(_request: Request, context: Context): Promise<NextResponse> {
  const { equipmentId } = await context.params;
  const { status, body } = await proxyDelete(
    `/api/v1/equipment/${encodeURIComponent(equipmentId)}`,
  );
  return body === null ? new NextResponse(null, { status }) : NextResponse.json(body, { status });
}
