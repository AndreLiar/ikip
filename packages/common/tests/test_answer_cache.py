"""Exact-match answer cache (Story 3.7 layer 4) — fakes, no network.

Skipped without langgraph. Verifies: miss computes + stores; hit replays identically
WITHOUT re-running the graph; abstention preserved on hit (AC5); cross-tenant isolation
(NFR10); superseded version => miss (FR14); ingestion invalidation => miss.
"""

import uuid

import pytest

pytest.importorskip("langgraph")

from ikip_common.cache import FakeCache, invalidate_tenant_answers  # noqa: E402
from ikip_common.llm import Claim, FakeChatClient, FakeGroundingValidator, GroundedAnswer  # noqa: E402
from ikip_common.llm.answer_cache import cached_grounded_answer  # noqa: E402
from ikip_common.llm.hybrid import RetrievalOutcome  # noqa: E402
from langchain_core.documents import Document  # noqa: E402

A = uuid.uuid4()
B = uuid.uuid4()


def _doc() -> Document:
    return Document(
        page_content="Fault E42: pump overheat.",
        metadata={
            "chunk_id": "c1",
            "document_id": "d1",
            "document_version_id": "v1",
            "revision": "A",
            "is_current": True,
            "section_id": "s1",
            "heading": "3.2",
            "hierarchy_path": "3.2",
            "page_start": 1,
            "page_end": 1,
        },
    )


def _retrieve_ok(q):
    return RetrievalOutcome(documents=[_doc()], abstained=False)


def _counting_chat() -> FakeChatClient:
    return FakeChatClient(
        GroundedAnswer(
            status="answered", claims=[Claim(text="E42 = overheat", evidence_markers=["E1"])]
        )
    )


def _call(cache, chat, tenant=A, *, versions=("v1",), retrieve=_retrieve_ok):
    return cached_grounded_answer(
        "What is E42?",
        cache=cache,
        tenant_id=tenant,
        current_version_ids=versions,
        retrieve=retrieve,
        chat_client=chat,
        validator=FakeGroundingValidator(),
        equipment_model="P1",
        revision="A",
    )


def test_miss_then_hit_without_recompute() -> None:
    cache, chat = FakeCache(), _counting_chat()
    r1, hit1 = _call(cache, chat)
    r2, hit2 = _call(cache, chat)
    assert hit1 is False and hit2 is True
    assert len(chat.calls) == 1  # graph (generation) ran only once
    assert r1.answer == r2.answer and r2.status == "answered"


def test_abstention_preserved_on_hit() -> None:
    cache = FakeCache()
    # cold run abstains (no evidence); the abstention must be cached + replayed as abstention
    chat = _counting_chat()
    r1, hit1 = _call(cache, chat, retrieve=lambda q: RetrievalOutcome(documents=[], abstained=True))
    r2, hit2 = _call(cache, chat, retrieve=lambda q: RetrievalOutcome(documents=[], abstained=True))
    assert hit1 is False and hit2 is True
    assert r1.status == "abstained" and r2.status == "abstained"
    assert chat.calls == []  # never generated


def test_cross_tenant_isolation() -> None:
    cache = FakeCache()
    _call(cache, _counting_chat(), tenant=A)
    _, hit_b = _call(cache, _counting_chat(), tenant=B)
    assert hit_b is False  # tenant B cannot read tenant A's cached answer (NFR10)


def test_superseded_version_is_a_miss() -> None:
    cache = FakeCache()
    _call(cache, _counting_chat(), versions=("v1",))
    _, hit = _call(cache, _counting_chat(), versions=("v2",))
    assert hit is False  # a new current-version set never serves the old answer (FR14)


def test_ingestion_invalidation_is_a_miss() -> None:
    cache = FakeCache()
    _call(cache, _counting_chat())
    invalidate_tenant_answers(cache, A)  # Dagster publishes a new version
    _, hit = _call(cache, _counting_chat())
    assert hit is False
