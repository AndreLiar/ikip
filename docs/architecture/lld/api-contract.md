# LLD — API Contract Skeleton (`/api/v1`)

_Hand-authored precursor to the generated OpenAPI (Story 4.1). All endpoints versioned under `/api/v1`, Pydantic-validated, tenant- and permission-scoped, authorize-before-retrieval. The generated spec supersedes this doc once the API exists. Unblocks Epic 4._

Conventions:
- **Auth:** bearer token (OIDC / Entra ID) carrying `tenant_id` + `role`; every request is tenant-scoped server-side.
- **IDs:** UUID. **Times:** ISO-8601 UTC. **Paging:** `?limit=&cursor=`.
- **Roles:** `admin` > `manager` > `technician` (least privilege per endpoint).

## Error envelope (all non-2xx)
```json
{ "error": { "code": "string", "message": "human readable", "details": {}, "trace_id": "uuid" } }
```
Status codes: `400` validation · `401` unauthenticated · `403` unauthorized / cross-tenant (no leakage) · `404` not found · `409` conflict · `422` semantic · `429` rate limit · `500` internal.

## Endpoints

| Method & path | Purpose | Role | Maps to |
|---|---|---|---|
| `GET /health` | liveness + dependency status | public | Story 1.3 |
| `GET /me` | current user + tenant + role | any | Story 1.6 |
| `POST /auth/token` | OIDC exchange / session | public | Story 1.6 |
| `GET/POST /organizations` | list/create tenants | admin | Story 4.7 |
| `GET/POST /workspaces` · `.../users` | workspace & user mgmt, role assign | admin/manager | Story 4.7 |
| `GET/POST /equipment` · `GET/PATCH/DELETE /equipment/{id}` | equipment catalog | manager | Story 4.3 |
| `POST /documents` | upload → async ingestion job | manager | Story 4.2 |
| `GET /documents` · `GET /documents/{id}` | browse/filter, detail | technician | Story 4.2 |
| `GET /documents/{id}/versions` | version history | technician | Story 4.2 |
| `GET /documents/{id}/file?page=` | presigned source for viewer @page | technician | Story 4.5 |
| `GET /ingestion-jobs` · `GET /ingestion-jobs/{id}` | job status/history | manager | Story 2.x, 4.2 |
| `POST /search` | keyword/semantic/hybrid + filters | technician | Story 3.3/3.4, 4.4 |
| `POST /assistant/query` | grounded answer (SSE stream) | technician | Story 3.5, 4.4 |
| `GET /conversations` · `GET /conversations/{id}` | history | technician | Story 4.6 |
| `POST /messages/{id}/feedback` | rate / flag answer | technician | Story 4.6 |
| `GET /evaluation/runs` · `GET /evaluation/runs/{id}` | eval results | manager | Epic 5 |
| `GET /ops/metrics` | latency/error/cost/pipeline health | manager | Story 5.6 |

## Representative shapes

### `POST /search`
```jsonc
// request
{ "query": "fault code E42 reset procedure",
  "mode": "hybrid",                         // keyword | semantic | hybrid
  "filters": { "manufacturer": "Siemens", "model": "S7-1500", "revision": "A", "only_current": true },
  "top_k": 10 }
// 200
{ "results": [
  { "chunk_id": "…", "score": 0.82,
    "document_id": "…", "document_version_id": "…", "revision": "A",
    "page_start": 142, "section": "3.2.1 Fault handling",
    "snippet": "…E42 indicates…" } ],
  "latency_ms": 180 }
```

### `POST /assistant/query`  (Server-Sent Events stream)
```jsonc
// request
{ "question": "How do I reset fault E42 on this unit?",
  "equipment_id": "…", "conversation_id": "…" }
// stream: token events, then a final event:
{ "type": "final",
  "answer": "… reset procedure …",
  "abstained": false,
  "citations": [ { "document_version_id": "…", "revision": "A", "page": 142, "section_id": "…" } ],
  "warnings": [ "De-energize before servicing." ],
  "trace_id": "…" }
// abstention case:
{ "type": "final", "abstained": true,
  "message": "Insufficient evidence for this model/revision.", "trace_id": "…" }
```

### `POST /documents`  (multipart upload)
```jsonc
// 202 Accepted
{ "document_id": "…", "ingestion_job_id": "…", "state": "pending" }
```

## Notes
- `assistant/query` **always** returns either a cited answer or an explicit `abstained:true` — never an unsupported answer (FR17); this is asserted by the safety suite (Story 5.3).
- Every endpoint resolves authorization **before** touching retrieval or source files (FR21); cross-tenant access returns `403` with no body leakage (NFR10).
- Rate limits / quotas (`429`) and audit logging apply per Story 4.8.
- Request/response bodies become Pydantic models; this table is the contract, the generated OpenAPI is the truth once Story 4.1 lands.
