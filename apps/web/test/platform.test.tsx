import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import PlatformPage from '@/app/platform/page';

function response(body: unknown, status = 200): Response {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('platform operations page', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(window, 'prompt').mockReturnValue('Factory A');
    fetchMock.mockImplementation(async (_input, init) =>
      init?.method === 'DELETE'
        ? response(null, 204)
        : response([
            {
              id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
              name: 'Factory A',
              configuration: {},
              policies: {},
              created_at: '2026-01-01T00:00:00Z',
            },
          ]),
    );
  });

  afterEach(() => vi.restoreAllMocks());

  it('lists organizations and sends the typed name for destructive deletion', async () => {
    render(<PlatformPage />);
    expect(await screen.findByText('Factory A')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Permanently delete' }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('expected_name=Factory+A'), {
        method: 'DELETE',
      }),
    );
  });
});
