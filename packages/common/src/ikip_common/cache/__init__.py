"""Caching: port + adapters + safe key design (Story 3.7, ADR 0009).

Port `Cache`; adapters `RedisCache` (default, lazy redis) + `FakeCache` (CI). Key
builders in `keys` carry the correctness (tenant partition, version-set fingerprint,
invalidation epoch). Layer 2 query-embedding cache here; the exact-match answer cache
(needs the grounded-answer AnswerResult) lives in `ikip_common.llm.answer_cache`.
Fuzzy/semantic "similar question" caching is explicitly out of scope (deferred).
"""

from ikip_common.cache.base import Cache
from ikip_common.cache.embedding import cached_query_embedding
from ikip_common.cache.fake import FakeCache
from ikip_common.cache.keys import (
    answer_key,
    current_answer_epoch,
    invalidate_tenant_answers,
    normalize,
    query_embedding_key,
    version_fingerprint,
)
from ikip_common.cache.redis import RedisCache


def build_cache(settings=None) -> Cache:  # noqa: ANN001
    """Build the production cache (Redis) from Settings. Tests inject FakeCache."""
    return RedisCache(settings)


__all__ = [
    "Cache",
    "RedisCache",
    "FakeCache",
    "build_cache",
    "cached_query_embedding",
    "answer_key",
    "query_embedding_key",
    "version_fingerprint",
    "normalize",
    "current_answer_epoch",
    "invalidate_tenant_answers",
]
