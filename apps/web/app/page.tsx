'use client';

import { useState } from 'react';
import Link from 'next/link';

import { AnswerPanel } from '@/components/AnswerPanel';
import { SearchResults } from '@/components/SearchResults';
import type { AskResponse, RetrieveResponse, SearchMode } from '@/lib/types';

type Tab = 'ask' | 'search';

export default function Home(): React.JSX.Element {
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<SearchMode>('hybrid');
  const [currentOnly, setCurrentOnly] = useState(true);
  const [equipmentModel, setEquipmentModel] = useState('');
  const [revision, setRevision] = useState('');
  const [tab, setTab] = useState<Tab>('ask');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [results, setResults] = useState<RetrieveResponse | null>(null);

  async function run(which: Tab): Promise<void> {
    if (query.trim() === '') return;
    setLoading(true);
    setError(null);
    setTab(which);
    setAnswer(null);
    setResults(null);
    try {
      if (which === 'ask') {
        const resp = await fetch('/api/ask', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query,
            equipment_model: equipmentModel || null,
            revision: revision || null,
          }),
        });
        if (!resp.ok) throw new Error(`ask failed (${resp.status})`);
        setAnswer((await resp.json()) as AskResponse);
      } else {
        const resp = await fetch('/api/retrieve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query, mode, current_only: currentOnly }),
        });
        if (!resp.ok) throw new Error(`search failed (${resp.status})`);
        setResults((await resp.json()) as RetrieveResponse);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'request failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="shell">
      <h1>IKIP — Technician Assistant</h1>
      <p className="sub">Ask a question or search the equipment documentation.</p>
      <nav>
        <Link href="/documents">Manage document library</Link>
        {' · '}
        <Link href="/admin">Administration</Link>
        {' · '}
        <Link href="/platform">Platform operations</Link>
      </nav>

      <form
        className="query-form"
        onSubmit={(e) => {
          e.preventDefault();
          void run('ask');
        }}
      >
        <textarea
          aria-label="question"
          placeholder="e.g. What does fault code E42 mean?"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={2}
        />

        <div className="filters">
          <label>
            Search mode
            <select
              aria-label="search mode"
              value={mode}
              onChange={(e) => setMode(e.target.value as SearchMode)}
            >
              <option value="hybrid">Hybrid</option>
              <option value="lexical">Keyword</option>
              <option value="vector">Semantic</option>
            </select>
          </label>
          <label>
            Equipment model
            <input
              aria-label="equipment model"
              value={equipmentModel}
              onChange={(e) => setEquipmentModel(e.target.value)}
              placeholder="optional"
            />
          </label>
          <label>
            Revision
            <input
              aria-label="revision"
              value={revision}
              onChange={(e) => setRevision(e.target.value)}
              placeholder="optional"
            />
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={currentOnly}
              onChange={(e) => setCurrentOnly(e.target.checked)}
            />
            Current versions only
          </label>
        </div>

        <div className="actions">
          <button type="submit" disabled={loading || query.trim() === ''}>
            Ask assistant
          </button>
          <button
            type="button"
            className="secondary"
            disabled={loading || query.trim() === ''}
            onClick={() => void run('search')}
          >
            Search passages
          </button>
        </div>
      </form>

      {loading ? <p className="status">Working…</p> : null}
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      {tab === 'ask' && answer ? <AnswerPanel answer={answer} /> : null}
      {tab === 'search' && results ? <SearchResults results={results} /> : null}
    </main>
  );
}
