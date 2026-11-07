"""Hybrid retrieval tests (Story 3.4): RRF fusion, reranker port, abstention.

Skipped when langchain_core is absent (fast CI `validate` without `embeddings`).
Pure: RRF algorithm, IdentityReranker, RetrievalOutcome. DB-gated: hybrid_retrieve
fuses both arms with citations, and abstains under score floors / no match (AC4).
"""

import os
import uuid

import pytest

pytest.importorskip("langchain_core")

from ikip_common.llm.hybrid import (  # noqa: E402
    IdentityReranker,
    RetrievalOutcome,
    hybrid_retrieve,
    reciprocal_rank_fusion,
)
from langchain_core.documents import Document  # noqa: E402


def _doc(cid: str) -> Document:
    return Document(page_content=cid, metadata={"chunk_id": cid})


# --- pure ------------------------------------------------------------------


def test_rrf_ranks_doc_in_both_lists_first() -> None:
    list_a = [_doc("a"), _doc("b"), _doc("c")]
    list_b = [_doc("b"), _doc("d")]
    fused = reciprocal_rank_fusion([list_a, list_b])
    assert fused[0].metadata["chunk_id"] == "b"  # appears high in both -> top
    assert {d.metadata["chunk_id"] for d in fused} == {"a", "b", "c", "d"}  # union, deduped
    assert all("rrf_score" in d.metadata for d in fused)


def test_rrf_empty_lists() -> None:
    assert reciprocal_rank_fusion([[], []]) == []


def test_identity_reranker_passthrough_and_topk() -> None:
    docs = [_doc("a"), _doc("b"), _doc("c")]
    r = IdentityReranker()
    assert [d.metadata["chunk_id"] for d in r.rerank("q", docs)] == ["a", "b", "c"]
    assert [d.metadata["chunk_id"] for d in r.rerank("q", docs, top_k=2)] == ["a", "b"]


def test_retrieval_outcome_shape() -> None:
    out = RetrievalOutcome(documents=[], abstained=True, reason="insufficient evidence")
    assert out.abstained and out.reason == "insufficient evidence"


# --- DB-backed -------------------------------------------------------------

_URL = os.environ.get("TEST_DATABASE_URL")
dbonly = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture(scope="module")
def engine():
    from ikip_common.db.base import Base
    from sqlalchemy import create_engine, text

    url = _URL.replace("postgresql://", "postgresql+psycopg://", 1) if _URL else _URL
    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


def _seed_chunk(session, tenant, content: str):
    from ikip_common.db.models import Chunk, DocumentVersion, Section
    from ikip_common.db.models import Document as Doc

    d = Doc(tenant_id=tenant.id, title="Manual", type="manual")
    session.add(d)
    session.flush()
    dv = DocumentVersion(document_id=d.id, revision="A", checksum=f"c-{uuid.uuid4()}")
    session.add(dv)
    session.flush()
    sec = Section(document_version_id=dv.id, heading="3.2", hierarchy_path="3.2")
    session.add(sec)
    session.flush()
    ch = Chunk(tenant_id=tenant.id, section_id=sec.id, content=content)
    session.add(ch)
    session.flush()
    return ch


@dbonly
def test_hybrid_fuses_both_arms_with_citations(engine) -> None:
    from ikip_common.db.embeddings import embed_and_store
    from ikip_common.db.models import Tenant
    from ikip_common.llm import FakeEmbeddingClient
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        t = Tenant(name="A")
        session.add(t)
        session.flush()
        ch = _seed_chunk(session, t, "Fault E42 indicates pump motor overheat.")
        client = FakeEmbeddingClient(dimensions=512)
        embed_and_store(session, t.id, client, [ch])
        session.flush()

        out = hybrid_retrieve(session, t.id, "E42 pump", client)
        assert not out.abstained
        assert len(out.documents) == 1
        assert out.documents[0].metadata["hierarchy_path"] == "3.2"
        assert "rrf_score" in out.documents[0].metadata
        session.rollback()


@dbonly
def test_hybrid_abstains_when_nothing_passes(engine) -> None:
    from ikip_common.db.embeddings import embed_and_store
    from ikip_common.db.models import Tenant
    from ikip_common.llm import FakeEmbeddingClient
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        t = Tenant(name="B")
        session.add(t)
        session.flush()
        ch = _seed_chunk(session, t, "Routine lubrication schedule for bearings.")
        client = FakeEmbeddingClient(dimensions=512)
        embed_and_store(session, t.id, client, [ch])
        session.flush()

        # lexical term matches nothing + an impossible cosine floor -> both arms empty.
        out = hybrid_retrieve(
            session, t.id, "zzqqxx", client, lexical_min_score=0.9, vector_min_score=2.0
        )
        assert out.abstained
        assert out.reason == "insufficient evidence"
        assert out.documents == []
        session.rollback()
