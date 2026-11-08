import type { SourceUrlResponse } from './types';

/**
 * Fetch a short-lived presigned URL for a cited document version (via the BFF) and open
 * it, jumping to the cited page when known (`#page=N`, honored by PDF viewers; a no-op
 * for text). Authorization happens server-side before the URL is issued (Story 4.5 AC3).
 */
export async function openSource(versionId: string, pageStart: number | null): Promise<void> {
  const resp = await fetch(`/api/documents/${versionId}/source-url`);
  if (!resp.ok) throw new Error(`source unavailable (${resp.status})`);
  const data = (await resp.json()) as SourceUrlResponse;
  const url = pageStart != null ? `${data.url}#page=${pageStart}` : data.url;
  window.open(url, '_blank', 'noopener,noreferrer');
}
