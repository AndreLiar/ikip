# MISSION-018 — Execution log

Evidence labels: `[verified]` run with output.

## Step 1 — Cache port + adapters — [verified]
`cache/base.py` `Cache` Protocol (get/set/delete/incr). `cache/redis.py` `RedisCache`
(lazy `redis`, from `REDIS_URL`). `cache/fake.py` `FakeCache` (in-memory). Dep group
`cache = ["redis>=5.0"]`.

## Step 2 — Safe key design (the correctness) — [verified]
`cache/keys.py` (pure): `normalize` (lowercase+ws, NOT semantic), `version_fingerprint`
(order-independent, changes on supersession), `query_embedding_key`, `answer_key`
(tenant + equipment + revision + version fingerprint + epoch), `current_answer_epoch`,
`invalidate_tenant_answers` (epoch bump for bulk invalidation).

## Step 3 — Cache layers — [verified]
Layer 2 `cache/embedding.py` `cached_query_embedding` (Cache + EmbeddingClient; safe/free).
Layer 4 `llm/answer_cache.py` `cached_grounded_answer`: builds the version-aware key,
returns `(AnswerResult, hit)`; on miss runs the graph and stores (abstentions included).
AnswerResult (de)serialization round-trips claims + resolved citations.
Layer 1 (embedding reuse) already enforced in Story 3.2.

## Step 4 — Tests + gate — [verified]
```
uv run pytest packages/common/tests/test_cache.py test_answer_cache.py -q   # 15 passed
uv run pytest packages/common/tests -q        # 80 passed, 30 skipped
uv run ruff check / format --check            # OK
```
- Pure (CI): normalization; version fingerprint order-independence/change; answer key
  tenant/equipment/revision/version/epoch sensitivity; FakeCache roundtrip; epoch invalidation;
  query-embedding hit skips recompute.
- Fakes (importorskip langgraph): miss→hit without re-running the graph; **abstention preserved
  on hit**; **cross-tenant isolation**; superseded version → miss; ingestion invalidation → miss.

## Step 5 — Live RedisCache — [verified]
Against Redis Cloud (`.env` REDIS_URL): set/get, incr (1→2), delete → None. `build_cache()` OK.

## Notes
- The cache is deliberately dumb; all correctness is in `cache.keys` behind the `Cache` port,
  so a backend swap (Docker/Redis Cloud/Azure Cache) can't leak across tenants.
- `cache.keys`/`cache.embedding` are langchain-free (fast CI). `llm/answer_cache` is heavy
  (imports the graph); its test `importorskip`s langgraph.
