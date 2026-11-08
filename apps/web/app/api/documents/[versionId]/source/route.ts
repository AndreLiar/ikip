import { proxyGet } from '@/lib/bff';

interface SourceUrlBody {
  url: string;
  content_type?: string | null;
}

// Same-origin PDF byte proxy for PDF.js. FastAPI authorizes first and returns a
// short-lived R2 URL; the BFF consumes it server-side, avoiding browser CORS.
export async function GET(
  _request: Request,
  context: { params: Promise<{ versionId: string }> },
): Promise<Response> {
  const { versionId } = await context.params;
  if (!/^[0-9a-fA-F-]{36}$/.test(versionId)) {
    return Response.json({ detail: 'invalid version id' }, { status: 400 });
  }
  const result = await proxyGet(`/api/v1/documents/${versionId}/source-url`);
  if (result.status !== 200) return Response.json(result.body, { status: result.status });
  const source = result.body as SourceUrlBody;
  const upstream = await fetch(source.url, { cache: 'no-store' });
  if (!upstream.ok || !upstream.body) {
    return Response.json({ detail: 'source fetch failed' }, { status: 502 });
  }
  return new Response(upstream.body, {
    status: 200,
    headers: {
      'Content-Type':
        source.content_type ?? upstream.headers.get('Content-Type') ?? 'application/pdf',
      'Cache-Control': 'private, no-store',
    },
  });
}
