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
