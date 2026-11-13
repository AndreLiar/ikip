"""Cache keys + FakeCache + query-embedding cache (Story 3.7) — pure, no network, CI.

The key design IS the correctness (ADR 0009): tenant partition, version-set
fingerprint, invalidation epoch, normalization.
"""

import uuid

from ikip_common.cache import (
    CachingEmbeddingClient,
    FakeCache,
    answer_key,
    cached_query_embedding,
    current_answer_epoch,
    invalidate_tenant_answers,
    normalize,
    query_embedding_key,
    version_fingerprint,
)
from ikip_common.llm import FakeEmbeddingClient


class _CountingClient:
    """Wraps FakeEmbeddingClient, counting embed() calls to prove caching skips them."""

    def __init__(self) -> None:
        self._inner = FakeEmbeddingClient(dimensions=8)
        self.calls = 0

    @property
    def model_version(self) -> str:
        return self._inner.model_version

    @property
    def dimensions(self) -> int:
        return self._inner.dimensions

    def embed(self, texts):  # noqa: ANN001, ANN201
        self.calls += 1
        return self._inner.embed(texts)


class _BoomCache:
    """A cache whose every op raises — proves CachingEmbeddingClient degrades gracefully."""

    def get(self, key):  # noqa: ANN001, ANN201
        raise RuntimeError("cache down")

    def set(self, key, value, *, ttl_s=None):  # noqa: ANN001, ANN201
        raise RuntimeError("cache down")

    def delete(self, key):  # noqa: ANN001, ANN201
        raise RuntimeError("cache down")

    def incr(self, key):  # noqa: ANN001, ANN201
        raise RuntimeError("cache down")


A = uuid.uuid4()
B = uuid.uuid4()


# --- normalization + fingerprint -------------------------------------------


def test_normalize() -> None:
    assert normalize("  Fault   E42\n") == "fault e42"


def test_version_fingerprint_order_independent_and_changes() -> None:
    assert version_fingerprint(["v1", "v2"]) == version_fingerprint(["v2", "v1"])
    assert version_fingerprint(["v1"]) != version_fingerprint(["v1", "v2"])
    assert version_fingerprint([]) == "none"


# --- answer key correctness ------------------------------------------------


def _key(tenant, *, question="E42?", model="P1", rev="A", vers=("v1",), epoch=0) -> str:
    return answer_key(
        tenant,
        question,
        equipment_model=model,
        revision=rev,
        current_version_ids=vers,
        epoch=epoch,
    )


def test_answer_key_is_tenant_partitioned() -> None:
    assert _key(A) != _key(B)  # same question, different tenant -> different key (NFR10)
    assert str(A) in _key(A)


def test_answer_key_version_aware() -> None:
    assert _key(A, vers=("v1",)) != _key(A, vers=("v2",))  # superseded version -> new key (FR14)


def test_answer_key_revision_and_equipment_aware() -> None:
    assert _key(A, rev="A") != _key(A, rev="B")
    assert _key(A, model="P1") != _key(A, model="P2")


def test_answer_key_epoch_invalidation() -> None:
    assert _key(A, epoch=0) != _key(A, epoch=1)


def test_query_embedding_key_depends_on_model_version() -> None:
    assert query_embedding_key("q", "m1@512") != query_embedding_key("q", "m2@512")
    assert query_embedding_key("Q ", "m1@512") == query_embedding_key("q", "m1@512")  # normalized


# --- FakeCache + epoch -----------------------------------------------------


def test_fake_cache_roundtrip_and_delete() -> None:
    c = FakeCache()
    assert c.get("k") is None
    c.set("k", "v", ttl_s=60)
    assert c.get("k") == "v" and c.ttls["k"] == 60
    c.delete("k")
    assert c.get("k") is None


def test_invalidate_bumps_epoch() -> None:
    c = FakeCache()
    assert current_answer_epoch(c, A) == 0
    assert invalidate_tenant_answers(c, A) == 1
    assert current_answer_epoch(c, A) == 1
    assert current_answer_epoch(c, B) == 0  # per-tenant


# --- query-embedding cache -------------------------------------------------


def test_cached_query_embedding_hit_skips_recompute() -> None:
    c = FakeCache()
    client = FakeEmbeddingClient(dimensions=8)
    v1 = cached_query_embedding(c, client, "pump overheat")
    # second call returns the cached vector (identical) without recomputing
    v2 = cached_query_embedding(c, client, "pump overheat")
    assert v1 == v2
    assert c.get(query_embedding_key("pump overheat", client.model_version)) is not None


# --- CachingEmbeddingClient (wired into retrieve/ask) ----------------------


class _RecordingMetrics:
    def __init__(self) -> None:
        self.caches: list[dict] = []

    def record_cache(self, *, cache: str, hit: bool) -> None:
        self.caches.append({"cache": cache, "hit": hit})


def test_caching_embedding_client_caches_single_query_and_records_metric() -> None:
    inner = _CountingClient()
    metrics = _RecordingMetrics()
    client = CachingEmbeddingClient(inner, FakeCache(), metrics=metrics)

    v1 = client.embed(["pump overheat"])
    v2 = client.embed(["pump overheat"])  # served from cache
    assert v1 == v2
    assert inner.calls == 1  # the Azure embed ran only once
    assert metrics.caches == [
        {"cache": "embedding", "hit": False},
        {"cache": "embedding", "hit": True},
    ]


def test_caching_embedding_client_passes_through_bulk() -> None:
    inner = _CountingClient()
    client = CachingEmbeddingClient(inner, FakeCache())
    client.embed(["chunk a", "chunk b", "chunk c"])  # build-time indexing: not cached
    client.embed(["chunk a", "chunk b", "chunk c"])
    assert inner.calls == 2  # each bulk call hits the client (no caching)


def test_caching_embedding_client_degrades_on_cache_outage() -> None:
    inner = _CountingClient()
    client = CachingEmbeddingClient(inner, _BoomCache())  # every cache op raises
    out = client.embed(["still works"])  # must not raise — direct embed
    assert out and inner.calls == 1
    assert client.model_version == inner.model_version
    assert client.dimensions == inner.dimensions
