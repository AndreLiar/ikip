# Concept — Caching: the key is a correctness feature

_Write-once concept note. First used by Story 3.7. Decision: [ADR 0009](../../adr/0009-caching-strategy.md). Relates to [grounded-answers](./grounded-answers.md), [multi-tenancy](./multi-tenancy.md)._

## Why caching here is not "just performance"
RAG is expensive (tokens, latency); the same question gets asked again. Caching cuts cost + p95. But in a **multi-tenant, version-aware, safety-sensitive** system a naive answer cache breaks three guarantees:
- **Tenant isolation** — keying on question text alone serves Tenant A's answer to Tenant B (disclosure, NFR10).
- **Version-awareness** — the right answer depends on equipment model/revision + which document version is current; a stale key serves an **obsolete procedure** (FR14).
- **Abstention/safety** — a stale "answered" must not be served when the system should now abstain (FR17).

So **the cache key + invalidation ARE the correctness** — not tuning knobs. "Redis or not" was never the question (Redis is already in the stack); *what to cache and how to key/invalidate it safely* is.

## The layered cache (ADR 0009)
| # | Layer | Key | Backend | Scope |
|---|---|---|---|---|
| 1 | Embedding reuse | `(chunk_id, model_version)` | Postgres (unique — Story 3.2) | done |
| 2 | Query-embedding | `(normalized_query, model_version)` | Redis TTL | MVP |
| 4 | Exact-match answer | `(tenant, normalized_question, equipment_model, revision, current_version_set, epoch)` | Redis TTL | MVP |
| 5 | Semantic "similar question" | embedding similarity within a tenant/version partition | Redis+vector | **deferred** |

Layer 1 is essentially free and already enforced (re-embedding skips existing `(chunk_id, model_version)`). Layer 2 has no safety surface (a query's embedding is the same for everyone). Layers 4/5 carry the hard rules below.

## Hard rules for the answer cache
1. **Tenant-partitioned key** — `tenant_id` is in the key; no entry is reachable cross-tenant. This is a security test, not a hope.
2. **Version-aware key** — the key encodes equipment model + revision + a **fingerprint of the current document-version set**. Supersede a version → the fingerprint changes → the old key is unreachable (an obsolete answer is never served).
3. **Invalidation on ingestion** — when Dagster publishes a new/superseded version, bump a per-tenant **epoch** (`incr`); the epoch is in the key, so all prior answers for that tenant become unreachable at once (cheap, no key scanning). Defense-in-depth with rule 2.
4. **A hit must not change abstention** — abstained results are cached and replayed **as abstentions**; a cache hit returns exactly what a cold run produced.
5. **Citations stay valid** — a cached answer keeps its citations, which still resolve to currently-valid versions (guaranteed by rule 2).

## Normalization (not semantics)
Question/query normalization = lowercase + collapse whitespace. Deterministic, so "E42?" and "  e42? " share a key — but it does **not** cross meaning. Fuzzy/semantic "similar question" matching (layer 5) is **explicitly out of scope** (deferred): it needs an embedding-similarity match *within* the same tenant/version partition + an eval gate proving hits don't change abstention. Not at MVP.

## Ports & adapters
`Cache` is a tiny port (`get`/`set`/`delete`/`incr`); `RedisCache` (lazy redis) is the default, `FakeCache` (in-memory) backs CI with no network. Backend is a config switch (local Docker Redis ↔ Redis Cloud ↔ Azure Cache). The cache is deliberately **dumb** — all correctness is in the key (`cache.keys`), so the store can't leak across tenants by accident.

## Rules to remember
1. The **key is a correctness feature**: tenant + equipment + revision + version-set + epoch.
2. Answer/retrieval hits are **tenant-partitioned** — cross-tenant isolation is tested (NFR10).
3. Superseded version ⇒ different key; ingestion ⇒ **epoch bump** ⇒ bulk invalidation (FR14).
4. A hit **replays the cold result**, including **abstention** (never silently "answered").
5. Layer 1 (embedding reuse) + layer 2 (query embedding) are safe/free; **semantic cache is deferred**.
6. Cache is dumb; correctness lives in `cache.keys`, behind the `Cache` port.

## Related
- Decision: [ADR 0009](../../adr/0009-caching-strategy.md).
- Concepts: [grounded-answers](./grounded-answers.md) · [hybrid-retrieval](./hybrid-retrieval.md) · [embeddings](./embeddings.md) · [multi-tenancy](./multi-tenancy.md) · [dedup-versioning](./dedup-versioning.md) (is_current / version set).
- Next: ingestion wires the invalidation hook on version publish (Epic 2/6); the semantic cache (layer 5) is a measured post-MVP addition.
