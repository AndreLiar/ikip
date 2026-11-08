import { NextResponse } from 'next/server';

import { proxyGet, proxyForm } from '@/lib/bff';

export async function GET(request: Request): Promise<NextResponse> {
  const query = new URL(request.url).searchParams.toString();
  const { status, body } = await proxyGet(`/api/v1/documents${query ? `?${query}` : ''}`);
  return NextResponse.json(body, { status });
}

export async function POST(request: Request): Promise<NextResponse> {
  const form = await request.formData();
  const file = form.get('file');
  if (!(file instanceof File) || file.size === 0) {
    return NextResponse.json({ detail: 'a non-empty file is required' }, { status: 400 });
  }
  const { status, body } = await proxyForm('/api/v1/documents/upload', form);
  return NextResponse.json(body, { status });
}
