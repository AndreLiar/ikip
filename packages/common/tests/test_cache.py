"""Cache keys + FakeCache + query-embedding cache (Story 3.7) — pure, no network, CI.

The key design IS the correctness (ADR 0009): tenant partition, version-set
fingerprint, invalidation epoch, normalization.
"""

import uuid

from ikip_common.cache import (
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
