import { NextResponse } from 'next/server';

import { proxyPatch } from '@/lib/bff';

export async function PATCH(
  request: Request,
  context: { params: Promise<{ documentId: string }> },
): Promise<NextResponse> {
  const { documentId } = await context.params;
  const payload = await request.json().catch(() => null);
  if (!payload || !Object.hasOwn(payload as object, 'type')) {
    return NextResponse.json({ detail: 'type is required' }, { status: 400 });
  }
  const { status, body } = await proxyPatch(
    `/api/v1/documents/${encodeURIComponent(documentId)}`,
    payload,
  );
  return NextResponse.json(body, { status });
}
