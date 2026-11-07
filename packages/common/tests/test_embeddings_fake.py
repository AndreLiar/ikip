"""FakeEmbeddingClient contract tests (Story 3.2) — pure, no network, CI.

The fake backs the EmbeddingClient port so generation + versioning logic is testable
without Azure. These assert the properties the store relies on: determinism, fixed
dimension, ordering, model_version tagging.
"""

import math

from ikip_common.llm import EmbeddingClient, FakeEmbeddingClient


def test_fake_client_satisfies_port() -> None:
    client = FakeEmbeddingClient()
    assert isinstance(client, EmbeddingClient)  # runtime_checkable Protocol


def test_deterministic_same_text_same_vector() -> None:
    a = FakeEmbeddingClient(dimensions=512).embed(["code défaut E42"])[0]
    b = FakeEmbeddingClient(dimensions=512).embed(["code défaut E42"])[0]
    assert a == b


def test_dimensions_and_unit_norm() -> None:
    client = FakeEmbeddingClient(dimensions=512)
    [vec] = client.embed(["pompe"])
    assert client.dimensions == 512
    assert len(vec) == 512
    assert math.isclose(math.sqrt(sum(x * x for x in vec)), 1.0, rel_tol=1e-9)


def test_distinct_texts_differ() -> None:
    client = FakeEmbeddingClient()
    v1, v2 = client.embed(["surchauffe moteur", "facture impayée"])
    assert v1 != v2


def test_embed_preserves_order_and_count() -> None:
    client = FakeEmbeddingClient(dimensions=8)
    texts = ["a", "b", "c"]
    vectors = client.embed(texts)
    assert len(vectors) == 3
    # order: re-embedding one text matches its position in the batch
    assert vectors[1] == client.embed(["b"])[0]


def test_model_version_tag() -> None:
    assert FakeEmbeddingClient(dimensions=512).model_version == "fake-embedding@512"
    assert FakeEmbeddingClient(dimensions=256).model_version == "fake-embedding@256"


def test_empty_input() -> None:
    assert FakeEmbeddingClient().embed([]) == []
