'use client';

import { useState } from 'react';

import type { Citation } from '@/lib/types';

import { SourceViewer } from './SourceViewer';

/**
 * A resolvable citation (FR16): document revision + section + page. Clickable — it opens
 * an in-app viewer of the cited source at the cited page (Story 4.5), via a short-lived
 * presigned URL. Region highlight is deferred (needs per-chunk bounding boxes at
 * extraction time).
 */
export function CitationChip({ citation }: { citation: Citation }): React.JSX.Element {
  const [open, setOpen] = useState(false);
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

  const content = (
    <>
      {label}
      {obsolete ? <span className="badge-obsolete"> obsolete</span> : null}
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
    <>
      <button
        type="button"
        className="citation citation--link"
        data-testid="citation"
        title={citation.heading ?? 'Open source'}
        onClick={() => setOpen(true)}
      >
        {content}
      </button>
      {open ? (
        <SourceViewer
          versionId={citation.document_version_id!}
          page={citation.page_start ?? null}
          regions={citation.regions as { page: number; bbox: [number, number, number, number] }[]}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  );
}
