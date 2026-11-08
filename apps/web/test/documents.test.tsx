import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import DocumentsPage from '@/app/documents/page';

const document = {
  id: 'd1',
  title: 'Pump Manual',
  type: 'manual',
  current_revision: 'B',
  version_count: 2,
  created_at: '2026-01-01T00:00:00Z',
};
const job = {
  id: 'j1',
  source: 'upload://pump.pdf',
  state: 'pending',
  attempts: 0,
  created_at: '2026-01-01T00:00:00Z',
};
const equipment = {
  id: 'e1',
  manufacturer: 'Siemens',
  model: 'S7-1500',
  revision: 'A',
  asset_id: 'LINE-1',
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('document library', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.startsWith('/api/documents?')) return response([document]);
      if (url === '/api/ingestion-jobs') return response([job]);
      if (url === '/api/equipment') return response([equipment]);
      if (url === '/api/documents/d1/versions') {
        return response([{ id: 'v1', revision: 'B', is_current: true }]);
      }
      if (url === '/api/documents/d1') return response({ ...document, type: 'datasheet' });
      if (url === '/api/equipment/e1/documents/d1') return new Response(null, { status: 204 });
      return response({}, 404);
    });
  });

  afterEach(() => vi.unstubAllGlobals());

  it('loads documents and visible ingestion status', async () => {
    render(<DocumentsPage />);
    expect(await screen.findByText('Pump Manual')).toBeInTheDocument();
    expect(screen.getByText('pending')).toBeInTheDocument();
  });

  it('loads version history on demand', async () => {
    render(<DocumentsPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Versions (2)' }));
    expect(await screen.findByText('B (current)')).toBeInTheDocument();
  });

  it('forwards title and type filters', async () => {
    render(<DocumentsPage />);
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'pump' } });
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'manual' } });
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/documents?query=pump&type=manual',
        expect.objectContaining({ cache: 'no-store' }),
      ),
    );
  });

  it('lets a manager categorize a document', async () => {
    render(<DocumentsPage />);
    const category = await screen.findByLabelText('Category for Pump Manual');
    fireEvent.change(category, { target: { value: 'datasheet' } });
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/documents/d1',
        expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ type: 'datasheet' }) }),
      ),
    );
  });

  it('associates a document with equipment', async () => {
    render(<DocumentsPage />);
    const selector = await screen.findByLabelText('Equipment for Pump Manual');
    fireEvent.change(selector, { target: { value: 'e1' } });
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/equipment/e1/documents/d1',
        expect.objectContaining({ method: 'PUT' }),
      ),
    );
  });
});
