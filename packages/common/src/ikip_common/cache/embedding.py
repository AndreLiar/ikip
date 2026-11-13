"""Query-embedding cache (Story 3.7 layer 2, ADR 0009).

Embedding the same query twice is wasteful; cache the vector by (normalized query,
model_version) with a TTL. Deterministic, no safety surface (not tenant/version
sensitive — a query's embedding is the same for everyone), so it's a pure cost/latency
win. Goes through the `Cache` + `EmbeddingClient` ports.
"""

from __future__ import annotations

import json

from ikip_common.cache.base import Cache
from ikip_common.cache.keys import query_embedding_key
from ikip_common.llm.base import EmbeddingClient, Vector

DEFAULT_TTL_S = 3600


def cached_query_embedding(
    cache: Cache, client: EmbeddingClient, query: str, *, ttl_s: int = DEFAULT_TTL_S
) -> Vector:
    """Return the query's embedding, reusing a cached vector when present."""
    key = query_embedding_key(query, client.model_version)
    hit = cache.get(key)
    if hit is not None:
        return json.loads(hit)
    [vector] = client.embed([query])
    cache.set(key, json.dumps(vector), ttl_s=ttl_s)
    return vector


class CachingEmbeddingClient:
    """EmbeddingClient decorator that caches SINGLE-text (query) embeddings (Story 3.7,
    ADR 0009), wired into the retrieve/ask paths.

    - Single-text `embed([query])` goes through the query-embedding cache → a hit skips the
      Azure call (cost + latency win); bulk `embed([...])` (build-time chunk indexing) passes
      straight through — each chunk is unique, not worth caching.
    - **Best-effort**: any cache backend error degrades to a direct embed. A cache outage
      must never break retrieval.
    - Optional `metrics` (Story 5.6 Metrics port) records cache hit/miss for the dashboard.
    """

    def __init__(
        self,
        inner: EmbeddingClient,
        cache: Cache,
        *,
        ttl_s: int = DEFAULT_TTL_S,
        metrics: object | None = None,
    ) -> None:
        self._inner = inner
        self._cache = cache
        self._ttl_s = ttl_s
        self._metrics = metrics

    @property
    def model_version(self) -> str:
        return self._inner.model_version

    @property
    def dimensions(self) -> int:
        return self._inner.dimensions

    def embed(self, texts):  # noqa: ANN001, ANN201 — Sequence[str] -> list[Vector]
        if len(texts) != 1:
            return self._inner.embed(texts)  # bulk indexing: don't cache
        query = texts[0]
        key = query_embedding_key(query, self._inner.model_version)
        try:
            hit = self._cache.get(key)
        except Exception:  # noqa: BLE001 — a cache outage must not break retrieval
            hit = None
        if hit is not None:
            self._record(hit=True)
            return [json.loads(hit)]
        self._record(hit=False)
        [vector] = self._inner.embed([query])
        try:
            self._cache.set(key, json.dumps(vector), ttl_s=self._ttl_s)
        except Exception:  # noqa: BLE001 — best-effort write
            pass
        return [vector]

    def _record(self, *, hit: bool) -> None:
        if self._metrics is not None:
            self._metrics.record_cache(cache="embedding", hit=hit)
