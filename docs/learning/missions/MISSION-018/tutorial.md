# MISSION-018 — Reproduction tutorial

Add layered caching behind the `Cache` port. Concept: [caching](../../concepts/caching.md);
decision [ADR 0009](../../../adr/0009-caching-strategy.md).

## Prerequisites
- Stories 3.2–3.6 done. For the real cache: `uv sync --group cache` (+ `embeddings` for the answer cache).
- `REDIS_URL` in `.env` (local Docker Redis or Redis Cloud).

## Query-embedding cache (layer 2)
```python
from ikip_common.cache import build_cache, cached_query_embedding
from ikip_common.llm import build_embedding_client

cache, client = build_cache(), build_embedding_client()
v = cached_query_embedding(cache, client, "pump overheat")   # miss → embeds + stores
v2 = cached_query_embedding(cache, client, "pump overheat")  # hit → cached, no API call
```

## Exact-match answer cache (layer 4)
```python
from ikip_common.cache import build_cache
from ikip_common.llm import build_chat_client
from ikip_common.llm.answer import make_hybrid_retrieve
from ikip_common.llm.answer_cache import cached_grounded_answer

result, hit = cached_grounded_answer(
    "What is fault E42?",
    cache=build_cache(),
    tenant_id=tenant_id,
    current_version_ids=[str(v) for v in current_document_version_ids],  # version-aware key
    retrieve=make_hybrid_retrieve(session, tenant_id, build_embedding_client()),
    chat_client=build_chat_client(),
    equipment_model="P-200", revision="A",
)
# `hit` tells you if it was served from cache; an abstention is cached + replayed as abstention
```

## Invalidate on ingestion (version publish)
```python
from ikip_common.cache import build_cache, invalidate_tenant_answers
# when Dagster publishes a new/superseded document_version for a tenant:
invalidate_tenant_answers(build_cache(), tenant_id)   # bumps the tenant's answer epoch
```

## Test (no network)
```bash
uv run pytest packages/common/tests/test_cache.py -q            # pure: keys, fake, query-embed
uv run pytest packages/common/tests/test_answer_cache.py -q     # fakes: hit/miss, isolation, invalidation
uv run ruff check packages/common && uv run ruff format --check packages/common
```

## Live Redis smoke
```bash
uv run python -c "
from dotenv import load_dotenv, find_dotenv; load_dotenv(find_dotenv(usecwd=True))
from ikip_common.cache import build_cache
c=build_cache(); c.set('t','v',ttl_s=10); print(c.get('t')); c.delete('t')"
```

## Common mistakes
- **Keying an answer on question text alone** → cross-tenant leak + stale version. Always use `answer_key` (tenant + equipment + revision + version set + epoch).
- **Not caching abstentions** → a hit could differ from a cold run. We cache + replay them.
- **Expecting fuzzy "similar question" hits** → out of scope (deferred); normalization is exact, not semantic.
- **Forgetting invalidation** → after publishing a version, `invalidate_tenant_answers` (or rely on the version-set fingerprint changing the key).
