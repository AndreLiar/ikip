import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CitationChip } from '@/components/CitationChip';
import type { Citation } from '@/lib/types';

function cite(over: Partial<Citation> = {}): Citation {
  return {
    chunk_id: 'c1',
    document_id: 'd1',
    document_version_id: 'v1',
    revision: 'A',
    is_current: true,
    section_id: 's1',
    heading: 'Pods',
    hierarchy_path: '3.2',
    page_start: 142,
    page_end: 142,
    score: 0.9,
    regions: [],
    ...over,
  };
}

afterEach(() => vi.restoreAllMocks());

describe('CitationChip', () => {
  it('renders the resolvable reference', () => {
    render(<CitationChip citation={cite()} />);
    expect(screen.getByTestId('citation')).toHaveTextContent('rev A');
    expect(screen.getByTestId('citation')).toHaveTextContent('p.142');
  });

  it('opens an in-app viewer at the cited page when clicked', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ url: 'https://r2/x.pdf', expires_s: 300 }),
      })),
    );

    render(<CitationChip citation={cite()} />);
    fireEvent.click(screen.getByTestId('citation'));

    // viewer opens and fetches a presigned URL via the BFF
    expect(screen.getByTestId('viewer')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('viewer-frame')).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith('/api/documents/v1/source-url');
    // the iframe points at the presigned URL, jumped to the cited page
    expect(screen.getByTestId('viewer-frame')).toHaveAttribute('src', 'https://r2/x.pdf#page=142');
  });

  it('closes the viewer', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ url: 'https://r2/x.pdf', expires_s: 300 }),
      })),
    );
    render(<CitationChip citation={cite()} />);
    fireEvent.click(screen.getByTestId('citation'));
    await waitFor(() => expect(screen.getByTestId('viewer-frame')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('close viewer'));
    expect(screen.queryByTestId('viewer')).not.toBeInTheDocument();
  });

  it('selects the PDF region viewer when a citation has bounding boxes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ url: 'https://r2/x.pdf', expires_s: 300 }),
      })),
    );
    render(
      <CitationChip citation={cite({ regions: [{ page: 142, bbox: [0.1, 0.2, 0.8, 0.3] }] })} />,
    );
    fireEvent.click(screen.getByTestId('citation'));
    await waitFor(() => expect(screen.getByTestId('pdf-highlight')).toBeInTheDocument());
    expect(screen.queryByTestId('viewer-frame')).not.toBeInTheDocument();
  });

  it('is a non-clickable span when there is no version id', () => {
    render(<CitationChip citation={cite({ document_version_id: null })} />);
    expect(screen.getByTestId('citation').tagName).toBe('SPAN');
  });

  it('shows an error if the source fetch fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) })),
    );
    render(<CitationChip citation={cite()} />);
    fireEvent.click(screen.getByTestId('citation'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });
});
