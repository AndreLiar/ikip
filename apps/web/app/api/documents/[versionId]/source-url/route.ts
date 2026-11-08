import { NextResponse } from 'next/server';

import { proxyGet } from '@/lib/bff';

// GET /api/documents/:versionId/source-url → proxies to the FastAPI endpoint, which
// authorizes the tenant then issues a short-lived R2 presigned URL (Story 4.5).
export async function GET(
  _request: Request,
  context: { params: Promise<{ versionId: string }> },
): Promise<NextResponse> {
  const { versionId } = await context.params;
  if (!/^[0-9a-fA-F-]{36}$/.test(versionId)) {
    return NextResponse.json({ detail: 'invalid version id' }, { status: 400 });
  }
  const { status, body } = await proxyGet(`/api/v1/documents/${versionId}/source-url`);
  return NextResponse.json(body, { status });
}
