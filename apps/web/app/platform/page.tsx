'use client';

import Link from 'next/link';
import { FormEvent, useCallback, useEffect, useState } from 'react';

import type { PlatformOrganization } from '@/lib/types';

export default function PlatformPage(): React.JSX.Element {
  const [organizations, setOrganizations] = useState<PlatformOrganization[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (): Promise<void> => {
    const response = await fetch('/api/platform/organizations');
    if (!response.ok) throw new Error(`organizations could not be loaded (${response.status})`);
    setOrganizations((await response.json()) as PlatformOrganization[]);
  }, []);

  useEffect(() => {
    void refresh().catch((reason: unknown) =>
      setError(reason instanceof Error ? reason.message : 'request failed'),
    );
  }, [refresh]);

  async function createOrganization(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    const response = await fetch('/api/platform/organizations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...data, configuration: {}, policies: {} }),
    });
    if (!response.ok) return setError(`organization creation failed (${response.status})`);
    form.reset();
    await refresh();
  }

  async function deleteOrganization(organization: PlatformOrganization): Promise<void> {
    const expectedName = window.prompt(
      `Permanent deletion cannot be undone. Type “${organization.name}” to confirm.`,
    );
    if (expectedName !== organization.name) return;
    const query = new URLSearchParams({ expected_name: expectedName });
    const response = await fetch(
      `/api/platform/organizations/${organization.id}?${query.toString()}`,
      { method: 'DELETE' },
    );
    if (!response.ok) return setError(`organization deletion failed (${response.status})`);
    await refresh();
  }

  return (
    <main className="shell library">
      <Link href="/">← Application</Link>
      <h1>Platform operations</h1>
      <p className="sub">
        Cross-tenant organization lifecycle. Access requires a separately configured platform
        operator identity.
      </p>
      {error ? (
        <p role="alert" className="error">
          {error}
        </p>
      ) : null}
      <h2>Create organization</h2>
      <form className="equipment-form" onSubmit={(event) => void createOrganization(event)}>
        <input aria-label="Organization name" name="name" required />
        <input aria-label="Initial admin email" name="admin_email" type="email" required />
        <button type="submit">Create organization</button>
      </form>
      <h2>Organizations</h2>
      <ul className="document-list">
        {organizations.map((organization) => (
          <li key={organization.id}>
            <span>{organization.name}</span>
            <button className="danger" onClick={() => void deleteOrganization(organization)}>
              Permanently delete
            </button>
          </li>
        ))}
      </ul>
    </main>
  );
}
