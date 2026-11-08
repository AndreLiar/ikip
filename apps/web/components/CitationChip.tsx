'use client';

import { useState } from 'react';

import { openSource } from '@/lib/source';
import type { Citation } from '@/lib/types';

/**
 * A resolvable citation (FR16): document revision + section + page. Clickable — it opens
 * the cited source via a short-lived presigned URL at the cited page (Story 4.5). Opening
 * a PDF at an exact page + highlight is the full 4.5; here we open whatever artifact is
 * stored (text today), jumping to `#page=N` when the source is a PDF.
 */
export function CitationChip({ citation }: { citation: Citation }): React.JSX.Element {
  const [error, setError] = useState(false);
  const parts: string[] = [];
  if (citation.revision) parts.push(`rev ${citation.revision}`);
  if (citation.hierarchy_path) parts.push(`§${citation.hierarchy_path}`);
  if (citation.page_start != null) {
    parts.push(
      citation.page_end && citation.page_end !== citation.page_start
        ? `p.${citation.page_start}-${citation.page_end}`
        : `p.${citation.page_start}`,
    );
  }
  const obsolete = citation.is_current === false;
  const label = parts.join(' · ') || 'source';
  const canOpen = Boolean(citation.document_version_id);

  async function open(): Promise<void> {
    if (!citation.document_version_id) return;
    setError(false);
    try {
      await openSource(citation.document_version_id, citation.page_start ?? null);
    } catch {
      setError(true);
    }
  }

  const content = (
    <>
      {label}
      {obsolete ? <span className="badge-obsolete"> obsolete</span> : null}
      {error ? <span className="badge-obsolete"> unavailable</span> : null}
    </>
  );

  if (!canOpen) {
    return (
      <span className="citation" data-testid="citation" title={citation.heading ?? undefined}>
        {content}
      </span>
    );
  }
  return (
    <button
      type="button"
      className="citation citation--link"
      data-testid="citation"
      title={citation.heading ?? 'Open source'}
      onClick={() => void open()}
    >
      {content}
    </button>
  );
}
