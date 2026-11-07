# MISSION-018 — Caching (deterministic + exact-match answer) (Epic 3, Story 3.7)

**Mode:** Autonome (implements the ratified ADR 0009) + knowledge transfer.
**Objective:** cut cost + latency behind a `Cache` port without breaking tenant isolation or version-awareness — layered cache where the key + invalidation ARE the correctness.
**Maps to:** Epic 3 / Story 3.7. Implements [ADR 0009](../../../adr/0009-caching-strategy.md). Closes Epic 3.

## Acceptance criteria
1. Embedding reuse — not regenerated when `(chunk_id, model_version)` exists (Postgres). — **[verified]** (Story 3.2 `embed_and_store` skip_existing + unique constraint; DB test `test_re_embedding_same_version_is_idempotent`)
2. Query-embedding cache + exact-match answer cache behind a `Cache` port (Redis). — **[verified]** (`Cache` port, `RedisCache` [live-verified], `FakeCache`; `cached_query_embedding`, `cached_grounded_answer`)
3. Answer cache keys tenant-partitioned + encode equipment model + revision + current version set; no cross-tenant hit, no superseded version. — **[verified]** (`answer_key`; tests for tenant/revision/equipment/version-set)
4. Invalidated when a new/superseded `document_version` is published. — **[verified]** (`invalidate_tenant_answers` epoch bump; test `test_ingestion_invalidation_is_a_miss`)
5. A cache hit doesn't change the abstention decision vs cold run; cross-tenant isolation tested. — **[verified]** (`test_abstention_preserved_on_hit`, `test_cross_tenant_isolation`)
6. Fuzzy/semantic caching out of scope. — **[verified]** (deferred; only deterministic normalization, documented)

## Deliverables
- `cache/base.py` `Cache` port; `cache/redis.py` `RedisCache` (lazy); `cache/fake.py` `FakeCache`.
- `cache/keys.py` (pure): `normalize`, `version_fingerprint`, `query_embedding_key`, `answer_key`, epoch helpers (`current_answer_epoch`, `invalidate_tenant_answers`).
- `cache/embedding.py` `cached_query_embedding` (layer 2).
- `llm/answer_cache.py` `cached_grounded_answer` (layer 4; AnswerResult (de)serialization; abstention preserved).
- Dep group `cache = ["redis>=5.0"]`.
- Tests: `test_cache.py` (11 pure), `test_answer_cache.py` (5 fakes/importorskip). Live RedisCache verified manually.

## Concepts
Introduces [caching](../../concepts/caching.md). Reuses [grounded-answers](../../concepts/grounded-answers.md), [multi-tenancy](../../concepts/multi-tenancy.md), [embeddings](../../concepts/embeddings.md), [dedup-versioning](../../concepts/dedup-versioning.md).
