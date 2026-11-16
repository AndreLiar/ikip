'use client';

import { useEffect, useRef, useState } from 'react';

export interface PdfRegion {
  page: number;
  bbox: [number, number, number, number];
  /** Visual-evidence kind (Epic 9, Story 9.3): a diagram/table region is labeled + styled
   * distinctly from a plain text highlight. Absent for text citations. */
  kind?: 'figure' | 'table' | 'schematic' | 'chart';
}

export function PdfRegionViewer({
  url,
  pageNumber,
  regions,
}: {
  url: string;
  pageNumber: number;
  regions: PdfRegion[];
}): React.JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let loadingTask: import('pdfjs-dist').PDFDocumentLoadingTask | null = null;
    void import('pdfjs-dist')
      .then(async (pdfjs) => {
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          'pdfjs-dist/build/pdf.worker.min.mjs',
          import.meta.url,
        ).toString();
        loadingTask = pdfjs.getDocument({ url });
        const pdf = await loadingTask.promise;
        const page = await pdf.getPage(pageNumber);
        if (cancelled || !canvasRef.current) return;
        const initial = page.getViewport({ scale: 1 });
        const available = canvasRef.current.parentElement?.clientWidth ?? initial.width;
        const viewport = page.getViewport({ scale: available / initial.width });
        const canvas = canvasRef.current;
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        const context = canvas.getContext('2d');
        if (!context) throw new Error('canvas unavailable');
        await page.render({ canvas, canvasContext: context, viewport }).promise;
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : 'PDF rendering failed');
      });
    return () => {
      cancelled = true;
      if (loadingTask) void loadingTask.destroy();
    };
  }, [pageNumber, url]);

  if (error)
    return (
      <p className="error" role="alert">
        {error}
      </p>
    );
  return (
    <div className="pdf-page" data-testid="pdf-page">
      <canvas ref={canvasRef} />
      {regions
        .filter((region) => region.page === pageNumber)
        .map((region, index) => {
          const [x0, y0, x1, y1] = region.bbox;
          const isVisual = Boolean(region.kind);
          return (
            <span
              className={isVisual ? 'pdf-highlight pdf-highlight--visual' : 'pdf-highlight'}
              data-testid="pdf-highlight"
              data-kind={region.kind}
              key={`${index}-${region.bbox.join('-')}`}
              style={{
                left: `${x0 * 100}%`,
                top: `${y0 * 100}%`,
                width: `${(x1 - x0) * 100}%`,
                height: `${(y1 - y0) * 100}%`,
              }}
            >
              {isVisual ? (
                <span className="pdf-highlight-label" data-testid="pdf-highlight-label">
                  {region.kind}
                </span>
              ) : null}
            </span>
          );
        })}
    </div>
  );
}
