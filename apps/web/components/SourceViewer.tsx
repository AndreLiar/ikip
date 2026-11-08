'use client';

import { useEffect, useState } from 'react';

import { fetchSourceUrl, withPage } from '@/lib/source';

import { PdfRegionViewer, type PdfRegion } from './PdfRegionViewer';

/**
 * In-app document viewer at the cited page (Story 4.5 AC1/AC4). Fetches a short-lived
 * presigned URL (authorize-before-serve) and renders the source in an <iframe> jumped to
 * `#page=N` — the browser's PDF engine honors the anchor for PDF sources; text/HTML just
 * opens. Region *highlight* (AC2) is deferred: it needs per-chunk bounding boxes captured
 * at extraction time, which we don't store yet.
 */
export function SourceViewer({
  versionId,
  page,
  onClose,
  regions = [],
}: {
  versionId: string;
  page: number | null;
  onClose: () => void;
  regions?: PdfRegion[];
}): React.JSX.Element {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    if (regions.length > 0) {
      setUrl(`/api/documents/${encodeURIComponent(versionId)}/source`);
      return () => {
        active = false;
      };
    }
    fetchSourceUrl(versionId)
      .then((u) => active && setUrl(withPage(u, page)))
      .catch((e) => active && setError(e instanceof Error ? e.message : 'failed'));
    return () => {
      active = false;
    };
  }, [versionId, page, regions.length]);

  return (
    <div className="viewer-overlay" role="dialog" aria-label="source document" data-testid="viewer">
      <div className="viewer">
        <div className="viewer-bar">
          <span>Source{page != null ? ` · page ${page}` : ''}</span>
          <button type="button" onClick={onClose} aria-label="close viewer">
            ✕
          </button>
        </div>
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : url && regions.length > 0 && page != null ? (
          <PdfRegionViewer url={url.split('#')[0] ?? url} pageNumber={page} regions={regions} />
        ) : url ? (
          <iframe
            className="viewer-frame"
            src={url}
            title="source document"
            data-testid="viewer-frame"
          />
        ) : (
          <p className="status">Loading source…</p>
        )}
      </div>
    </div>
  );
}
