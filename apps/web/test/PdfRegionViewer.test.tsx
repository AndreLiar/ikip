import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PdfRegionViewer } from '@/components/PdfRegionViewer';

// pdfjs renders to <canvas> (unavailable in jsdom), so we mock it. The value under test
// is the HIGHLIGHT OVERLAY math + page filter — pure DOM over the regions. A hoisted flag
// lets one test force the pdf-load failure path.
const state = vi.hoisted(() => ({ fail: false }));

vi.mock('pdfjs-dist', () => {
  const viewport = { width: 100, height: 140 };
  const page = { getViewport: () => viewport, render: () => ({ promise: Promise.resolve() }) };
  return {
    GlobalWorkerOptions: { workerSrc: '' },
    getDocument: () => ({
      promise: state.fail
        ? Promise.reject(new Error('pdf load failed'))
        : Promise.resolve({ getPage: () => Promise.resolve(page) }),
      destroy: () => undefined,
    }),
  };
});

beforeEach(() => {
  state.fail = false;
  // jsdom's getContext returns null → stub a truthy 2d context so render proceeds.
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ({})) as never;
});

afterEach(() => vi.restoreAllMocks());

const REGIONS = [
  { page: 1, bbox: [0.1, 0.2, 0.5, 0.3] as [number, number, number, number] },
  { page: 2, bbox: [0.0, 0.0, 1.0, 1.0] as [number, number, number, number] },
];

describe('PdfRegionViewer', () => {
  it('renders the page and overlays only the current page regions', async () => {
    render(<PdfRegionViewer url="https://r2/x.pdf" pageNumber={1} regions={REGIONS} />);

    await waitFor(() => expect(screen.getByTestId('pdf-page')).toBeInTheDocument());
    const highlights = screen.getAllByTestId('pdf-highlight');
    // only the page-1 region is overlaid (page-2 region filtered out)
    expect(highlights).toHaveLength(1);
    // page-normalized bbox → percentage box (toBeCloseTo: avoid float noise)
    const s = highlights[0]!.style;
    const pct = (v: string): number => parseFloat(v);
    expect(pct(s.left)).toBeCloseTo(10); // x0 * 100
    expect(pct(s.top)).toBeCloseTo(20); // y0 * 100
    expect(pct(s.width)).toBeCloseTo(40); // (x1-x0) * 100
    expect(pct(s.height)).toBeCloseTo(10); // (y1-y0) * 100
  });

  it('shows an error when pdf rendering fails', async () => {
    state.fail = true;
    render(<PdfRegionViewer url="https://r2/x.pdf" pageNumber={1} regions={REGIONS} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });
});
