import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { FeedbackBar } from '@/components/FeedbackBar';

afterEach(() => vi.restoreAllMocks());

function okFetch(): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, json: async () => ({ id: 'f1' }) })),
  );
}

describe('FeedbackBar', () => {
  it('rates helpful via the BFF and confirms', async () => {
    okFetch();
    render(<FeedbackBar messageId="11111111-1111-1111-1111-111111111111" />);
    fireEvent.click(screen.getByLabelText('helpful'));
    await waitFor(() => expect(screen.getByTestId('feedback-done')).toBeInTheDocument());
    const call = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(call[0]).toBe('/api/feedback/11111111-1111-1111-1111-111111111111');
    expect(JSON.parse((call[1] as RequestInit).body as string).rating).toBe(1);
  });

  it('flags an issue (flagged + negative rating)', async () => {
    okFetch();
    render(<FeedbackBar messageId="11111111-1111-1111-1111-111111111111" />);
    fireEvent.click(screen.getByLabelText('flag issue'));
    await waitFor(() => expect(screen.getByTestId('feedback-done')).toBeInTheDocument());
    const body = JSON.parse(
      ((fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0]![1] as RequestInit)
        .body as string,
    );
    expect(body.flagged).toBe(true);
    expect(body.rating).toBe(-1);
  });

  it('shows an error when the request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) })),
    );
    render(<FeedbackBar messageId="11111111-1111-1111-1111-111111111111" />);
    fireEvent.click(screen.getByLabelText('helpful'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });
});
