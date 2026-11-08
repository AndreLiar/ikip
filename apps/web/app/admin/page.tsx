'use client';

import Link from 'next/link';
import { FormEvent, useCallback, useEffect, useState } from 'react';

import type { AdminUser, Organization, Workspace } from '@/lib/types';

export default function AdminPage(): React.JSX.Element {
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (): Promise<void> => {
    const [orgResponse, usersResponse, workspacesResponse] = await Promise.all([
      fetch('/api/admin/organization'),
      fetch('/api/admin/users'),
      fetch('/api/admin/workspaces'),
    ]);
    if (!orgResponse.ok || !usersResponse.ok || !workspacesResponse.ok) {
      throw new Error('administration data could not be loaded');
    }
    setOrganization((await orgResponse.json()) as Organization);
    setUsers((await usersResponse.json()) as AdminUser[]);
    setWorkspaces((await workspacesResponse.json()) as Workspace[]);
  }, []);

  useEffect(() => {
    void refresh().catch((reason: unknown) =>
      setError(reason instanceof Error ? reason.message : 'request failed'),
    );
  }, [refresh]);

  async function createUser(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const element = event.currentTarget;
    const data = Object.fromEntries(new FormData(element));
    const response = await fetch('/api/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...data, account_status: 'active' }),
    });
    if (!response.ok) return setError(`user creation failed (${response.status})`);
    element.reset();
    await refresh();
  }

  async function createWorkspace(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const element = event.currentTarget;
    const data = Object.fromEntries(new FormData(element));
    const response = await fetch('/api/admin/workspaces', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) return setError(`workspace creation failed (${response.status})`);
    element.reset();
    await refresh();
  }

  return (
    <main className="shell library">
      <Link href="/">← Application</Link>
      <h1>Administration</h1>
      <p className="sub">{organization?.name ?? 'Organization'} · users, roles and workspaces</p>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      <h2>Users</h2>
      <form className="equipment-form" onSubmit={(event) => void createUser(event)}>
        <input aria-label="User email" name="email" type="email" required />
        <select aria-label="User role" name="role" defaultValue="technician">
          <option value="technician">Technician</option>
          <option value="manager">Manager</option>
          <option value="admin">Admin</option>
        </select>
        <button type="submit">Add user</button>
      </form>
      <ul>
        {users.map((user) => (
          <li key={user.id}>
            {user.email} · {user.role}
          </li>
        ))}
      </ul>
      <h2>Workspaces</h2>
      <form className="equipment-form" onSubmit={(event) => void createWorkspace(event)}>
        <input aria-label="Workspace name" name="name" required />
        <button type="submit">Add workspace</button>
      </form>
      <ul>
        {workspaces.map((workspace) => (
          <li key={workspace.id}>{workspace.name}</li>
        ))}
      </ul>
    </main>
  );
}
