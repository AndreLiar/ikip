import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import EquipmentPage from '@/app/equipment/page';

const item = {
  id: 'e1',
  manufacturer: 'ABB',
  model: 'ACS880',
  revision: '2',
  asset_id: 'LINE-7',
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('equipment catalog', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.startsWith('/api/equipment?')) return response([item]);
      if (url === '/api/equipment' && init?.method === 'POST') return response(item, 201);
      if (url === '/api/equipment/e1' && init?.method === 'DELETE') {
        return new Response(null, { status: 204 });
      }
      return response({}, 404);
    });
  });

  afterEach(() => vi.unstubAllGlobals());

  it('browses equipment', async () => {
    render(<EquipmentPage />);
    expect(await screen.findByText(/ABB ACS880/)).toBeInTheDocument();
    expect(screen.getByText(/LINE-7/)).toBeInTheDocument();
  });

  it('creates equipment', async () => {
    render(<EquipmentPage />);
    fireEvent.change(screen.getByLabelText('Manufacturer'), { target: { value: 'ABB' } });
    fireEvent.change(screen.getByLabelText('Model'), { target: { value: 'ACS880' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add equipment' }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/equipment',
        expect.objectContaining({ method: 'POST' }),
      ),
    );
  });

  it('deletes equipment', async () => {
    render(<EquipmentPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/equipment/e1', { method: 'DELETE' }),
    );
  });
});
