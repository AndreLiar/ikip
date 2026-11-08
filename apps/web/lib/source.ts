import type { SourceUrlResponse } from './types';

/**
 * Fetch a short-lived presigned URL for a cited document version (via the BFF).
 * Authorization happens server-side before the URL is issued (Story 4.5 AC3).
 */
export async function fetchSourceUrl(versionId: string): Promise<string> {
  const resp = await fetch(`/api/documents/${versionId}/source-url`);
  if (!resp.ok) throw new Error(`source unavailable (${resp.status})`);
  const data = (await resp.json()) as SourceUrlResponse;
  return data.url;
}

/** Append a page anchor honored by browser PDF viewers (#page=N); no-op for text. */
export function withPage(url: string, pageStart: number | null): string {
  return pageStart != null ? `${url}#page=${pageStart}` : url;
}
