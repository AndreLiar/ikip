import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import AdminPage from '@/app/admin/page';

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('administration page', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === '/api/admin/organization') {
        return response({ id: 't1', name: 'Factory A', policies: {} });
      }
      if (url === '/api/admin/users') {
        return response([
          { id: 'u1', email: 'tech@example.com', role: 'technician', account_status: 'active' },
        ]);
      }
      if (url === '/api/admin/workspaces') return response([{ id: 'w1', name: 'Plant 1' }]);
      return new Response(null, { status: 404 });
    });
  });

  afterEach(() => vi.unstubAllGlobals());

  it('shows the tenant-scoped users and workspaces', async () => {
    render(<AdminPage />);
    expect(await screen.findByText(/Factory A/)).toBeInTheDocument();
    expect(screen.getByText(/tech@example.com/)).toBeInTheDocument();
    expect(screen.getByText('Plant 1')).toBeInTheDocument();
  });
});
