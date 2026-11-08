import { NextResponse } from 'next/server';

import { proxyGet } from '@/lib/bff';

export async function GET(): Promise<NextResponse> {
  const { status, body } = await proxyGet('/api/v1/ingestion-jobs');
  return NextResponse.json(body, { status });
}
