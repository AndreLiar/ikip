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

  it('opens the source (presigned, at the cited page) when clicked', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ url: 'https://r2/x', expires_s: 300 }),
      })),
    );
    const openSpy = vi.fn();
    vi.stubGlobal('open', openSpy);

    render(<CitationChip citation={cite()} />);
    fireEvent.click(screen.getByTestId('citation'));

    await waitFor(() => expect(openSpy).toHaveBeenCalled());
    expect(fetch).toHaveBeenCalledWith('/api/documents/v1/source-url');
    expect(openSpy).toHaveBeenCalledWith('https://r2/x#page=142', '_blank', expect.any(String));
  });

  it('is a non-clickable span when there is no version id', () => {
    render(<CitationChip citation={cite({ document_version_id: null })} />);
    expect(screen.getByTestId('citation').tagName).toBe('SPAN');
  });

  it('shows unavailable if the source fetch fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) })),
    );
    render(<CitationChip citation={cite()} />);
    fireEvent.click(screen.getByTestId('citation'));
    await waitFor(() => expect(screen.getByTestId('citation')).toHaveTextContent('unavailable'));
  });
});
