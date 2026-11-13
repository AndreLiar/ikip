# 0009. Caching strategy (layered, safety-first; Redis + Postgres backed)

- **Status:** Accepted
- **Date:** 2026-11-06
- **Deciders:** Architect, PM
- **Related:** FR10, FR14, FR17, FR21, FR31 · NFR1, NFR2, NFR10 · Epic 3 (Story 3.7), Epic 5 · relates to [ADR 0001](./0001-vector-store-pgvector.md), [ADR 0003](./0003-local-first-ports-and-adapters.md), [ADR 0007](./0007-pluggable-llm-client-azure-openai.md)

## Context
RAG is expensive on tokens and latency; repeated/similar work (re-embedding, repeated queries, the same question asked again) is common. Caching can cut cost and improve p95 latency (NFR1) and time-to-first-token (NFR2). But in IKIP a cache is **not** a pure performance concern — a naive answer cache would break three core guarantees:

- **Tenant isolation (FR21, NFR10):** a cache keyed on question text alone would serve Tenant A's answer to Tenant B — a cross-tenant disclosure.
- **Version-awareness (FR14):** the correct answer depends on equipment model/revision and which document version is current; "similar" questions about different revisions must not share an answer, or an obsolete procedure is served.
- **Abstention/safety (FR17, Story 5.3):** a stale cached answer could be served when the system should now abstain.

So the **cache key and invalidation are correctness features**, not tuning details. "Redis vs not" was never the question — Redis is already in the stack (as `JobQueue`); the open question was *what to cache and how to key/invalidate it safely*.

## Decision
Adopt a **layered cache**, accessed through a `Cache` **port** (local Redis ↔ prod Redis/Azure Cache; ports & adapters per [ADR 0003](./0003-local-first-ports-and-adapters.md)). Deterministic layers and an exact-match answer cache are **MVP**; fuzzy semantic caching is **deferred**.

| # | Layer | Key | Backend | Scope |
|---|-------|-----|---------|-------|
| 1 | **Embedding cache** | `(chunk_id, model_version)` | **Postgres** (`embedding` UNIQUE — already exists, [ADR 0001](./0001-vector-store-pgvector.md)) | MVP |
| 2 | **Query-embedding cache** | `(normalized_query, model_version)` | Redis (TTL) | MVP |
| 3 | **Retrieval cache** *(optional)* | `(tenant_id, normalized_query, filters, index_version)` | Redis (TTL) | MVP-optional |
| 4 | **Exact-match answer cache** | `(tenant_id, normalized_question, equipment_model, revision, current_version_set)` | Redis (TTL) | MVP |
| 5 | **Semantic ("similar question") cache** | embedding-similarity match **within** the same `(tenant_id, equipment_model, revision, version_set)` partition, above a threshold | Redis + vector | **Deferred (post-MVP)** |

**Hard rules for any answer/retrieval cache (4, 5):**
1. Key is **always tenant-partitioned** — no entry is reachable across tenants. Cross-tenant cache isolation is a security test (extends Story 6.2).
2. Key **encodes equipment model + revision + the current document-version set** — a superseded version invalidates the entry.
3. **Invalidation on ingestion:** when Dagster publishes a new/ superseded `document_version`, dependent cache entries are evicted.
4. A cache hit must **not** change the abstention decision vs. a cold run (verified for the deferred semantic layer by an eval check).
5. Cached answers retain their citations; citations must still resolve to currently-valid versions.

## Update (2026-11-13) — prompt caching evaluated + embedding cache wired + hit-rate metrics

A review asked "should we add prompt caching too?". Decision, recording three distinct caches:

1. **Answer cache (exact-match)** — *kept* (already here): tenant + query + equipment/revision + current-version epoch; caches abstentions too (safety-first); version-aware invalidation. Highest-value cache (a hit skips retrieval + embedding + generation).
2. **Query-embedding cache** — *now wired* (it existed as `cached_query_embedding` but wasn't on the live path). `CachingEmbeddingClient` decorates the `EmbeddingClient` in `/retrieve` + `/ask`: a repeated single query reuses its vector (skips the Azure embed); **bulk** (build-time chunk indexing) passes through; **best-effort** (a cache outage degrades to a direct embed — never breaks retrieval). No safety surface (a query's embedding is identical for everyone).
3. **Provider prompt caching (Azure OpenAI prefix cache)** — *deferred*. It discounts a shared prompt **prefix ≥ 1024 tokens**. Our `/ask` prompt is `[system ~200 tok] + [retrieved evidence — varies every query] + [question]`: the only stable prefix (system prompt) is **below the 1024-token threshold**, and the token-heavy evidence is different each call → caching wouldn't trigger, and padding the prefix to reach the threshold would *raise* per-call tokens (only ~50% discounted on a hit) — net-negative on misses. Revisit only if a measured, large fixed prefix emerges (few-shot, big fixed policy) and the cost dashboard shows LLM input tokens are the bottleneck.
4. **Semantic ("similar question") caching** — *rejected* (safety). A near-match could return the wrong procedure or an outdated-revision answer, breaking the grounding/abstention guarantees (Stories 3.5/5.3).

**Measure before optimizing:** a `ikip_cache_requests_total{cache,result}` metric (Story 5.6) now feeds a cache-hit-rate panel, so answer/embedding cache effectiveness is observable before any further caching work.

## Consequences
**Positive**
- Layers 1–2 are deterministic, zero-safety-surface cost/latency wins; layer 1 is essentially free (already in Postgres).
- Exact-match answer cache serves the common "same question again" case within the correct tenant+version context, cutting tokens (FR31) and TTFT (NFR2).
- Behind a port → backend swappable; no code coupling to Redis specifically.

**Negative / risks**
- Cache invalidation adds coupling between the ingestion pipeline (Dagster) and the cache (new eviction path on version supersession).
- An answer cache adds a second place where tenant/version correctness must be tested.
- TTL tuning is a real knob; too long risks staleness, too short wastes the cache.

**Neutral**
- On Azure, caching may use a small Redis/Azure Cache instance — this is the justified case for the "dedicated managed Redis" the tech stack deferred, introduced only when measured.

## Redis backend note (dev vs prod)
Redis backs both the `Cache` (this ADR) and the `JobQueue` ([ADR 0003](./0003-local-first-ports-and-adapters.md)). Backend choice per environment:

- **Dev:** either **local Docker Redis** (free, fast, offline) **or** **Redis Cloud Free (30 MB, best-effort SLA)** — both $0. Redis Cloud Free fits a "fully-managed dev" setup (Neon + R2 + Redis Cloud + Azure OpenAI, only the app local). 30 MB is adequate because the cache is **evictable (LRU)** and MVP job payloads are small (IDs/refs, not documents). Note: this is **convenience, not a cost saving** — unlike R2/Neon, Docker Redis was already free; and a remote Redis adds network latency to cache/queue ops.
- **Prod:** **not** the 30 MB free tier (too small; best-effort SLA conflicts with the 99.5% target, NFR3). Cache → a sized **Azure Cache for Redis** / paid Redis tier; durable job queue → **Azure Service Bus** (retries/dead-letter, Story 2.6) rather than a tiny Redis.

Both are reached through the `Cache` / `JobQueue` ports, so the backend is a config switch.

## Alternatives Considered
- **No caching (current state):** simplest, but leaves obvious cost/latency on the table and re-embeds needlessly. Rejected.
- **Naive semantic cache keyed on question text:** highest value, but violates tenant isolation and version-awareness as described. Rejected for MVP; allowed later only under the hard rules above.
- **In-process/application memory cache:** no extra infra, but not shared across API/worker replicas and lost on restart. Rejected as the primary mechanism (fine as an L1 in front of Redis later).

## Revisit When
- Measured token cost / TTFT justifies building the **semantic cache** (layer 5) — implement with the hard rules + an eval gate proving cache hits don't change abstention or citation correctness.
- Cache hit-rate is low enough that a layer isn't worth its invalidation complexity (drop that layer).
- On Azure, cache load justifies a dedicated managed Redis tier.

> Honest framing (consistent with the other ADRs): Redis is the obvious, already-present backend — the real work is the **key design + invalidation**, which is what makes caching safe in a multi-tenant, version-aware, safety-sensitive system rather than a cross-tenant leak.
