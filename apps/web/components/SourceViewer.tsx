'use client';

import { useEffect, useState } from 'react';

import { fetchSourceUrl, withPage } from '@/lib/source';

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
}: {
  versionId: string;
  page: number | null;
  onClose: () => void;
}): React.JSX.Element {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchSourceUrl(versionId)
      .then((u) => active && setUrl(withPage(u, page)))
      .catch((e) => active && setError(e instanceof Error ? e.message : 'failed'));
    return () => {
      active = false;
    };
  }, [versionId, page]);

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
