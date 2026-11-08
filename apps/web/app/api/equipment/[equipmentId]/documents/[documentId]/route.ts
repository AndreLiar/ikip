import { NextResponse } from 'next/server';

import { proxyDelete, proxyPut } from '@/lib/bff';

type Context = { params: Promise<{ equipmentId: string; documentId: string }> };

function path(equipmentId: string, documentId: string): string {
  return `/api/v1/equipment/${encodeURIComponent(equipmentId)}/documents/${encodeURIComponent(documentId)}`;
}

export async function PUT(_request: Request, context: Context): Promise<NextResponse> {
  const { equipmentId, documentId } = await context.params;
  const { status, body } = await proxyPut(path(equipmentId, documentId));
  return body === null ? new NextResponse(null, { status }) : NextResponse.json(body, { status });
}

export async function DELETE(_request: Request, context: Context): Promise<NextResponse> {
  const { equipmentId, documentId } = await context.params;
  const { status, body } = await proxyDelete(path(equipmentId, documentId));
  return body === null ? new NextResponse(null, { status }) : NextResponse.json(body, { status });
}
