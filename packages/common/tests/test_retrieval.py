"""Lexical + vector search tests (Story 3.3).

Pure part (CI): compile the statements and assert the right SQL shape (simple FTS
config, @@, ts_rank, cosine <=>, tenant filter, citation joins) — no DB needed.
DB part (gated on TEST_DATABASE_URL): real tsvector + pgvector search, citation
refs, model_version filtering, tenant isolation.
"""

import os
import uuid

import pytest
from ikip_common.db.base import Base
from ikip_common.db.embeddings import embed_and_store
from ikip_common.db.models import Chunk, Document, DocumentVersion, Section, Tenant
from ikip_common.db.retrieval import (
    RetrievalFilters,
    _lexical_stmt,
    _vector_stmt,
    lexical_search,
    vector_search,
)
from ikip_common.llm import FakeEmbeddingClient
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

# --- pure: SQL shape -------------------------------------------------------


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect())).lower()


def test_lexical_stmt_uses_simple_fts_and_rank() -> None:
    from ikip_common.db.models import FTS_CONFIG

    assert FTS_CONFIG == "simple"  # language-neutral config (decision)
    sql = _sql(_lexical_stmt(uuid.uuid4(), "fault E42", 10, None))
    assert "websearch_to_tsquery" in sql
    assert "@@" in sql  # tsvector match
    assert "ts_rank" in sql  # ranking
    assert "tenant_id" in sql  # tenant scoping (NFR10)


def test_lexical_stmt_joins_citation_chain() -> None:
    sql = _sql(_lexical_stmt(uuid.uuid4(), "x", 5, None))
    assert "join section" in sql and "join document_version" in sql and "join document" in sql


def test_vector_stmt_uses_cosine_and_filters_model_version() -> None:
    sql = _sql(_vector_stmt(uuid.uuid4(), [0.1] * 512, "m1@512", 10, None))
    assert "<=>" in sql  # pgvector cosine distance
    assert "model_version" in sql  # only same-version vectors are comparable
    assert "tenant_id" in sql


def test_filters_add_version_type_equipment_and_metadata_clauses() -> None:
    filters = RetrievalFilters(
        current_only=True,
        document_type="manual",
        equipment_id=uuid.uuid4(),
        metadata={"equip": "P1"},
    )
    sql = _sql(_lexical_stmt(uuid.uuid4(), "x", 10, filters))
    assert "is_current is true" in sql  # version-awareness WHERE (applicable vs obsolete)
    assert "document.type" in sql  # equipment/document kind
    assert "document_equipment" in sql
    assert "@>" in sql  # JSONB containment for metadata (equipment model/revision)


def test_current_only_false_omits_is_current_predicate() -> None:
    sql = _sql(_lexical_stmt(uuid.uuid4(), "x", 10, RetrievalFilters(current_only=False)))
    assert "is_current is true" not in sql  # no version-awareness WHERE predicate


# --- DB-backed -------------------------------------------------------------

_URL = os.environ.get("TEST_DATABASE_URL")
dbonly = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture(scope="module")
def engine():
    url = _URL.replace("postgresql://", "postgresql+psycopg://", 1) if _URL else _URL
    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s
        s.rollback()


def _chunk(session: Session, tenant: Tenant, content: str) -> Chunk:
    d = Document(tenant_id=tenant.id, title="Manual")
    session.add(d)
    session.flush()
    dv = DocumentVersion(document_id=d.id, revision="A", checksum=f"c-{uuid.uuid4()}")
    session.add(dv)
    session.flush()
    sec = Section(document_version_id=dv.id, heading="3.2 Faults", hierarchy_path="3.2")
    session.add(sec)
    session.flush()
    ch = Chunk(tenant_id=tenant.id, section_id=sec.id, content=content)
    session.add(ch)
    session.flush()
    return ch


@dbonly
def test_lexical_search_finds_by_term_with_citation(session: Session) -> None:
    t = Tenant(name="A")
    session.add(t)
    session.flush()
    _chunk(session, t, "Fault E42 indicates pump motor overheat.")
    _chunk(session, t, "Routine lubrication schedule for bearings.")
    session.flush()

    hits = lexical_search(session, t.id, "E42", limit=10)
    assert len(hits) == 1
    assert "E42" in hits[0].content
    # citation chain present (FR16)
    assert hits[0].revision == "A" and hits[0].hierarchy_path == "3.2"
    assert hits[0].document_id and hits[0].document_version_id and hits[0].section_id


@dbonly
def test_vector_search_returns_results_with_citation_and_version_filter(session: Session) -> None:
    t = Tenant(name="A")
    session.add(t)
    session.flush()
    ch = _chunk(session, t, "Fault E42 indicates pump motor overheat.")
    client = FakeEmbeddingClient(dimensions=512, model_version="m1")
    embed_and_store(session, t.id, client, [ch])
    session.flush()

    [qvec] = client.embed(["pump overheating fault"])
    hits = vector_search(session, t.id, qvec, model_version="m1@512", limit=10)
    assert len(hits) == 1
    assert hits[0].chunk_id == ch.id
    assert hits[0].hierarchy_path == "3.2"
    # a different model_version yields nothing (only comparable vectors)
    assert vector_search(session, t.id, qvec, model_version="other@512", limit=10) == []


@dbonly
def test_search_is_tenant_scoped(session: Session) -> None:
    a, b = Tenant(name="A"), Tenant(name="B")
    session.add_all([a, b])
    session.flush()
    ch = _chunk(session, a, "Fault E42 pump motor overheat.")
    embed_and_store(session, a.id, FakeEmbeddingClient(dimensions=512), [ch])
    session.flush()

    assert len(lexical_search(session, a.id, "E42", limit=10)) == 1
    assert lexical_search(session, b.id, "E42", limit=10) == []  # NFR10
    [qvec] = FakeEmbeddingClient(dimensions=512).embed(["pump"])
    assert vector_search(session, b.id, qvec, model_version="fake-embedding@512", limit=10) == []
