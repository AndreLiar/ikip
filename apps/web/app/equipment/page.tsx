'use client';

import Link from 'next/link';
import { FormEvent, useCallback, useEffect, useState } from 'react';

import type { Equipment } from '@/lib/types';

export default function EquipmentPage(): React.JSX.Element {
  const [items, setItems] = useState<Equipment[]>([]);
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (): Promise<void> => {
    const params = new URLSearchParams();
    if (query.trim()) params.set('query', query.trim());
    const response = await fetch(`/api/equipment?${params}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`catalog failed (${response.status})`);
    setItems((await response.json()) as Equipment[]);
  }, [query]);

  useEffect(() => {
    void refresh().catch((reason: unknown) =>
      setError(reason instanceof Error ? reason.message : 'request failed'),
    );
  }, [refresh]);

  async function create(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const element = event.currentTarget;
    const form = new FormData(element);
    const response = await fetch('/api/equipment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.fromEntries(form)),
    });
    if (!response.ok) {
      setError(`create failed (${response.status})`);
      return;
    }
    element.reset();
    await refresh();
  }

  async function remove(id: string): Promise<void> {
    const response = await fetch(`/api/equipment/${id}`, { method: 'DELETE' });
    if (!response.ok) {
      setError(`delete failed (${response.status})`);
      return;
    }
    await refresh();
  }

  return (
    <main className="shell library">
      <Link href="/documents">← Document library</Link>
      <h1>Equipment catalog</h1>
      <p className="sub">Manage equipment models and physical asset identifiers.</p>
      <form className="equipment-form" onSubmit={(event) => void create(event)}>
        <input aria-label="Manufacturer" name="manufacturer" placeholder="Manufacturer" required />
        <input aria-label="Model" name="model" placeholder="Model" required />
        <input aria-label="Revision" name="revision" placeholder="Revision" />
        <input aria-label="Asset ID" name="asset_id" placeholder="Asset ID" />
        <button type="submit">Add equipment</button>
      </form>
      <label>
        Search equipment
        <input value={query} onChange={(event) => setQuery(event.target.value)} />
      </label>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      <ul className="document-list">
        {items.map((item) => (
          <li key={item.id}>
            <span>
              <strong>
                {item.manufacturer} {item.model}
              </strong>{' '}
              {item.revision ?? ''} · {item.asset_id ?? 'no asset ID'}
            </span>
            <button className="secondary" type="button" onClick={() => void remove(item.id)}>
              Delete
            </button>
          </li>
        ))}
      </ul>
    </main>
  );
}
