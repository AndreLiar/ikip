# MISSION-019 — Wire Epic 3 open hooks: cache invalidation at ingestion + hybrid-retrieval endpoint

**Mode:** Autonome (integration wiring of already-decided pieces) + knowledge transfer.
**Objective:** connect the two seams Epic 3 left open — (1) ingestion invalidates the answer cache when a document version is published; (2) the hybrid retrieval + grounded answer are reachable over HTTP, tenant-scoped.
**Maps to:** closes Epic 3 integration gaps. Applies [ADR 0009](../../../adr/0009-caching-strategy.md) (cache invalidation), [ADR 0021](../../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md), [ADR 0022](../../../adr/0022-grounded-answer-langgraph-gpt5-mini.md).

## What was wired
### 1. Cache invalidation on version publish
- `ikip_ingestion/version_publish.py` `publish_document_version(repo, cache, **kwargs)` — wraps `DocumentRepository.ingest_version` then bumps the tenant's answer epoch (`invalidate_tenant_answers`). Exact-duplicate → raises, no invalidation. Dagster-free + port-injected.
- Dagster `document_versions` asset now builds the cache and invalidates after publishes (`new_documents + new_versions`).
- **Decision:** the hook lives at the **ingestion layer**, not inside the DB repo — `ingest_version` stays a pure persistence operation; the cache coupling is the pipeline's concern (keeps `ikip_common.db` cache-free).

### 2. Hybrid-retrieval + ask endpoints
- `ikip_api/retrieval.py`: `POST /api/v1/retrieve` (hybrid retrieval, Story 3.4) and `POST /api/v1/ask` (cached grounded answer, Stories 3.5 + 3.7). Both **tenant-scoped by the authenticated Principal** (FR21/NFR10); citations in the response (FR16); abstention surfaced explicitly.
- **Decision:** heavy deps (langchain/langgraph, Azure) are **lazy-imported inside dependency providers**, so `create_app()` still imports in the fast CI `validate` job (no `embeddings` group). Providers are FastAPI dependencies → tests override them with fakes (no network/DB).

## Acceptance (self-set)
1. Publish invalidates the tenant answer cache; exact-dup doesn't. — **[verified]** (`test_version_publish.py`, FakeCache)
2. `/retrieve` requires auth, binds to the caller's tenant, returns citations, surfaces abstention, validates input. — **[verified]** (`test_retrieval_endpoint.py`)
3. `/ask` returns a grounded answer shape incl. not-certified notice + cache_hit. — **[verified]**
4. `create_app()` imports with no heavy group (lazy). — **[verified]** (smoke import)
5. No regression. — **[verified]** (139 passed, 35 skipped repo-wide; ruff/format OK)

## Deliverables
- `services/ingestion/src/ikip_ingestion/version_publish.py` + `tests/test_version_publish.py`.
- `services/ingestion/.../definitions.py` `document_versions` asset wired to invalidate.
- `apps/api/src/ikip_api/retrieval.py` (router + schemas + injectable services) + `main.py` mount.
- `apps/api/tests/test_retrieval_endpoint.py` (renamed to avoid a basename clash with `packages/common/tests/test_retrieval.py`).

## Concepts
Reuses [caching](../../concepts/caching.md), [hybrid-retrieval](../../concepts/hybrid-retrieval.md), [grounded-answers](../../concepts/grounded-answers.md), [auth-rbac](../../concepts/auth-rbac.md), [multi-tenancy](../../concepts/multi-tenancy.md).
