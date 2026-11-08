import { NextResponse } from 'next/server';

import { proxyGet } from '@/lib/bff';

export async function GET(
  _request: Request,
  context: { params: Promise<{ documentId: string }> },
): Promise<NextResponse> {
  const { documentId } = await context.params;
  const { status, body } = await proxyGet(
    `/api/v1/documents/${encodeURIComponent(documentId)}/versions`,
  );
  return NextResponse.json(body, { status });
}
