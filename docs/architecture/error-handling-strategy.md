# Error Handling Strategy

_Sharded from `../architecture.md`. Part of the [architecture index](./index.md)._

- Ingestion: retries with backoff; dead-letter path; errors recorded on `IngestionJob`; quality report surfaces failures.
- API: consistent error envelope; validation errors via Pydantic; auth/authz errors as 401/403 with no tenant leakage.
- RAG: on insufficient evidence → abstain (not error); on tool/retrieval failure → safe fallback + trace.
- All errors structured-logged and traced (OpenTelemetry); no secrets/PII in logs.
