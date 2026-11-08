'use client';

import Link from 'next/link';
import { FormEvent, useCallback, useEffect, useState } from 'react';

import type { DocumentSummary, DocumentVersion, IngestionJob } from '@/lib/types';

export default function DocumentsPage(): React.JSX.Element {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [versions, setVersions] = useState<Record<string, DocumentVersion[]>>({});
  const [query, setQuery] = useState('');
  const [documentType, setDocumentType] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async (): Promise<void> => {
    const params = new URLSearchParams();
    if (query.trim()) params.set('query', query.trim());
    if (documentType.trim()) params.set('type', documentType.trim());
    const [documentResponse, jobResponse] = await Promise.all([
      fetch(`/api/documents?${params}`, { cache: 'no-store' }),
      fetch('/api/ingestion-jobs', { cache: 'no-store' }),
    ]);
    if (!documentResponse.ok || !jobResponse.ok) throw new Error('library could not be loaded');
    setDocuments((await documentResponse.json()) as DocumentSummary[]);
    setJobs((await jobResponse.json()) as IngestionJob[]);
  }, [documentType, query]);

  useEffect(() => {
    void refresh().catch((reason: unknown) =>
      setError(reason instanceof Error ? reason.message : 'request failed'),
    );
  }, [refresh]);

  async function upload(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch('/api/documents', {
        method: 'POST',
        body: new FormData(event.currentTarget),
      });
      if (!response.ok) throw new Error(`upload failed (${response.status})`);
      event.currentTarget.reset();
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'upload failed');
    } finally {
      setBusy(false);
    }
  }

  async function toggleVersions(documentId: string): Promise<void> {
    if (versions[documentId]) {
      setVersions((current) => {
        const next = { ...current };
        delete next[documentId];
        return next;
      });
      return;
    }
    const response = await fetch(`/api/documents/${documentId}/versions`);
    if (!response.ok) {
      setError(`version history failed (${response.status})`);
      return;
    }
    const history = (await response.json()) as DocumentVersion[];
    setVersions((current) => ({
      ...current,
      [documentId]: history,
    }));
  }

  async function categorize(documentId: string, documentType: string): Promise<void> {
    const response = await fetch(`/api/documents/${documentId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: documentType || null }),
    });
    if (!response.ok) {
      setError(`categorization failed (${response.status})`);
      return;
    }
    await refresh();
  }

  return (
    <main className="shell library">
      <Link href="/">← Technician assistant</Link>
      <h1>Document library</h1>
      <p className="sub">Upload manuals, track ingestion, and inspect retained revisions.</p>

      <form className="upload-form" onSubmit={(event) => void upload(event)}>
        <label>
          Document file
          <input name="file" type="file" required />
        </label>
        <button disabled={busy} type="submit">
          {busy ? 'Uploading…' : 'Upload'}
        </button>
      </form>

      <div className="filters">
        <label>
          Title
          <input value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
        <label>
          Type
          <input value={documentType} onChange={(event) => setDocumentType(event.target.value)} />
        </label>
      </div>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      <h2>Documents</h2>
      {documents.length === 0 ? <p className="status">No matching documents.</p> : null}
      <ul className="document-list">
        {documents.map((document) => (
          <li key={document.id}>
            <div>
              <strong>{document.title}</strong> · {document.type ?? 'uncategorized'} · revision{' '}
              {document.current_revision ?? '—'}
            </div>
            <button
              className="secondary"
              type="button"
              onClick={() => void toggleVersions(document.id)}
            >
              Versions ({document.version_count})
            </button>
            <label>
              Category
              <select
                aria-label={`Category for ${document.title}`}
                value={document.type ?? ''}
                onChange={(event) => void categorize(document.id, event.target.value)}
              >
                <option value="">Uncategorized</option>
                <option value="manual">Manual</option>
                <option value="maintenance-manual">Maintenance manual</option>
                <option value="datasheet">Datasheet</option>
                <option value="procedure">Procedure</option>
              </select>
            </label>
            {versions[document.id] ? (
              <ul>
                {(versions[document.id] ?? []).map((version) => (
                  <li key={version.id}>
                    {version.revision}
                    {version.is_current ? ' (current)' : ''}
                  </li>
                ))}
              </ul>
            ) : null}
          </li>
        ))}
      </ul>

      <h2>Recent ingestion jobs</h2>
      <ul className="job-list">
        {jobs.map((job) => (
          <li key={job.id}>
            <code>{job.source}</code> <span className={`job job--${job.state}`}>{job.state}</span>
          </li>
        ))}
      </ul>
    </main>
  );
}
