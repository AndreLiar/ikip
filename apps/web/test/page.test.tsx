import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Home from '@/app/page';
import type { AskResponse, RetrieveResponse } from '@/lib/types';

afterEach(() => vi.restoreAllMocks());

function mockFetch(body: unknown, ok = true): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok, status: ok ? 200 : 500, json: async () => body }) as Response),
  );
}

const ANSWER: AskResponse = {
  status: 'answered',
  answer: 'A Pod is the smallest deployable unit. [E1]',
  claims: [
    { text: 'A Pod is the smallest deployable unit.', safety_critical: false, citations: [] },
  ],
  warnings: [],
  abstention_reason: null,
  not_certified_notice: 'not certified',
  cache_hit: false,
  conversation_id: 'conv-1',
  message_id: 'msg-1',
};

describe('Home (technician assistant)', () => {
  it('asks the assistant and renders the grounded answer', async () => {
    mockFetch(ANSWER);
    render(<Home />);
    fireEvent.change(screen.getByLabelText('question'), {
      target: { value: 'What is a Pod?' },
    });
    fireEvent.click(screen.getByRole('button', { name: /ask assistant/i }));

    await waitFor(() => expect(screen.getByTestId('answer')).toBeInTheDocument());
    expect(screen.getByText(/smallest deployable unit/)).toBeInTheDocument();
    // the browser called the same-origin BFF route, not the API directly (no token in browser)
    expect(fetch).toHaveBeenCalledWith('/api/ask', expect.objectContaining({ method: 'POST' }));
    // the persisted turn (message_id) surfaces the feedback bar (Story 4.6 glue)
    expect(screen.getByTestId('feedback')).toBeInTheDocument();
  });

  it('searches passages in the selected mode', async () => {
    const results: RetrieveResponse = {
      abstained: false,
      results: [
        {
          content: 'A Pod is a group of one or more containers.',
          citation: {
            chunk_id: 'c1',
            document_id: 'd1',
            document_version_id: 'v1',
            revision: 'A',
            is_current: true,
            section_id: 's1',
            heading: 'Pods',
            hierarchy_path: '1.1',
            page_start: 1,
            page_end: 1,
            score: 0.8,
          },
        },
      ],
    };
    mockFetch(results);
    render(<Home />);
    fireEvent.change(screen.getByLabelText('question'), { target: { value: 'pod' } });
    fireEvent.change(screen.getByLabelText('search mode'), { target: { value: 'lexical' } });
    fireEvent.click(screen.getByRole('button', { name: /search passages/i }));

    await waitFor(() => expect(screen.getByTestId('search-results')).toBeInTheDocument());
    expect(screen.getByText(/group of one or more containers/)).toBeInTheDocument();
    const call = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(call[0]).toBe('/api/retrieve');
    expect(JSON.parse((call[1] as RequestInit).body as string).mode).toBe('lexical');
  });

  it('shows an error when the request fails', async () => {
    mockFetch({ detail: 'boom' }, false);
    render(<Home />);
    fireEvent.change(screen.getByLabelText('question'), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: /ask assistant/i }));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });
});
