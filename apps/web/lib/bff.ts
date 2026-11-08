// BFF (backend-for-frontend) helper — runs ONLY server-side (route handlers).
// Forwards a request to the FastAPI service with a server-held bearer token, so the
// browser never sees the token and no CORS is needed (Story 4.4 AC4).

const API_URL = process.env.IKIP_API_URL ?? 'http://localhost:8000';
const API_TOKEN = process.env.IKIP_API_TOKEN ?? '';

export interface UpstreamResult {
  status: number;
  body: unknown;
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (API_TOKEN) headers['Authorization'] = `Bearer ${API_TOKEN}`;
  return headers;
}

export async function proxyPost(path: string, payload: unknown): Promise<UpstreamResult> {
  const resp = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
    cache: 'no-store',
  });
  const body = await resp.json().catch(() => ({ detail: 'invalid upstream response' }));
  return { status: resp.status, body };
}

export async function proxyPatch(path: string, payload: unknown): Promise<UpstreamResult> {
  const resp = await fetch(`${API_URL}${path}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(payload),
    cache: 'no-store',
  });
  const body = await resp.json().catch(() => ({ detail: 'invalid upstream response' }));
  return { status: resp.status, body };
}

export async function proxyPut(path: string, payload?: unknown): Promise<UpstreamResult> {
  const resp = await fetch(`${API_URL}${path}`, {
    method: 'PUT',
    headers: authHeaders(),
    body: payload === undefined ? undefined : JSON.stringify(payload),
    cache: 'no-store',
  });
  const body = await resp.json().catch(() => null);
  return { status: resp.status, body };
}

export async function proxyDelete(path: string): Promise<UpstreamResult> {
  const resp = await fetch(`${API_URL}${path}`, {
    method: 'DELETE',
    headers: authHeaders(),
    cache: 'no-store',
  });
  const body = await resp.json().catch(() => null);
  return { status: resp.status, body };
}

export async function proxyGet(path: string): Promise<UpstreamResult> {
  const resp = await fetch(`${API_URL}${path}`, {
    method: 'GET',
    headers: authHeaders(),
    cache: 'no-store',
  });
  const body = await resp.json().catch(() => ({ detail: 'invalid upstream response' }));
  return { status: resp.status, body };
}

export async function proxyForm(path: string, form: FormData): Promise<UpstreamResult> {
  const headers: Record<string, string> = {};
  if (API_TOKEN) headers['Authorization'] = `Bearer ${API_TOKEN}`;
  const resp = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers,
    body: form,
    cache: 'no-store',
  });
  const body = await resp.json().catch(() => ({ detail: 'invalid upstream response' }));
  return { status: resp.status, body };
}
