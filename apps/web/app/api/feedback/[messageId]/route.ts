import { NextResponse } from 'next/server';

import { proxyPost } from '@/lib/bff';

// POST /api/feedback/:messageId → proxies to POST /api/v1/messages/:id/feedback (Story 4.6).
export async function POST(
  request: Request,
  context: { params: Promise<{ messageId: string }> },
): Promise<NextResponse> {
  const { messageId } = await context.params;
  if (!/^[0-9a-fA-F-]{36}$/.test(messageId)) {
    return NextResponse.json({ detail: 'invalid message id' }, { status: 400 });
  }
  const payload = await request.json().catch(() => ({}));
  const { status, body } = await proxyPost(`/api/v1/messages/${messageId}/feedback`, payload);
  return NextResponse.json(body, { status });
}
