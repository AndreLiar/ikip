"""Embedding storage tests (Story 3.2, ADR 0020/0021) — the acceptance criteria.

DB-backed (pgvector) -> gated on TEST_DATABASE_URL (ephemeral Neon branch in CI).
Uses the deterministic FakeEmbeddingClient so no Azure call is needed. Covers:
cross-tenant isolation (NFR10), citation chain integrity (FR16), model-version
coexistence + additive/idempotent re-embedding (FR14).
"""

import os
import uuid

import pytest
from ikip_common.db.base import Base
from ikip_common.db.embeddings import embed_and_store, vectors_for_chunk
from ikip_common.db.models import (
    Chunk,
    Document,
    DocumentVersion,
    Embedding,
    Section,
    Tenant,
)
from ikip_common.db.repository import TenantScopedRepository
from ikip_common.llm import FakeEmbeddingClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")


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


class _EmbeddingRepo(TenantScopedRepository[Embedding]):
    model = Embedding


def _chunk(session: Session, tenant: Tenant) -> Chunk:
    d = Document(tenant_id=tenant.id, title="Manual")
    session.add(d)
    session.flush()
    dv = DocumentVersion(document_id=d.id, revision="A", checksum=f"c-{uuid.uuid4()}")
    session.add(dv)
    session.flush()
    sec = Section(document_version_id=dv.id, heading="3.2 Fault Handling", hierarchy_path="3.2")
    session.add(sec)
    session.flush()
    ch = Chunk(tenant_id=tenant.id, section_id=sec.id, content="Fault E42: pump motor overheat.")
    session.add(ch)
    session.flush()
    return ch


def test_embed_and_store_persists_vector_with_version(session: Session) -> None:
    t = Tenant(name="A")
    session.add(t)
    session.flush()
    ch = _chunk(session, t)

    client = FakeEmbeddingClient(dimensions=512, model_version="m1")
    report = embed_and_store(session, t.id, client, [ch])
    session.flush()

    assert report.embedded == 1 and report.skipped == 0
    assert report.model_version == "m1@512"
    rows = _EmbeddingRepo(session, t.id).list()
    assert len(rows) == 1
    assert rows[0].chunk_id == ch.id
    assert rows[0].model_version == "m1@512"
    assert len(list(rows[0].vector)) == 512


def test_re_embedding_same_version_is_idempotent(session: Session) -> None:
    t = Tenant(name="A")
    session.add(t)
    session.flush()
    ch = _chunk(session, t)
    client = FakeEmbeddingClient(dimensions=512, model_version="m1")

    embed_and_store(session, t.id, client, [ch])
    session.flush()
    report2 = embed_and_store(session, t.id, client, [ch])
    session.flush()

    assert report2.embedded == 0 and report2.skipped == 1
    assert len(_EmbeddingRepo(session, t.id).list()) == 1  # no duplicate


def test_new_model_version_is_additive_not_destructive(session: Session) -> None:
    t = Tenant(name="A")
    session.add(t)
    session.flush()
    ch = _chunk(session, t)

    embed_and_store(session, t.id, FakeEmbeddingClient(dimensions=512, model_version="m1"), [ch])
    session.flush()
    embed_and_store(session, t.id, FakeEmbeddingClient(dimensions=512, model_version="m2"), [ch])
    session.flush()

    vectors = vectors_for_chunk(session, t.id, ch.id)
    versions = {v.model_version for v in vectors}
    assert versions == {"m1@512", "m2@512"}  # prior vector preserved (FR14)


def test_tenant_isolation(session: Session) -> None:
    a, b = Tenant(name="A"), Tenant(name="B")
    session.add_all([a, b])
    session.flush()
    ch = _chunk(session, a)
    embed_and_store(session, a.id, FakeEmbeddingClient(dimensions=512), [ch])
    session.flush()

    assert len(_EmbeddingRepo(session, a.id).list()) == 1
    assert _EmbeddingRepo(session, b.id).list() == []  # tenant B sees nothing (NFR10)


def test_embedding_resolves_citation_chain(session: Session) -> None:
    t = Tenant(name="A")
    session.add(t)
    session.flush()
    ch = _chunk(session, t)
    embed_and_store(session, t.id, FakeEmbeddingClient(dimensions=512), [ch])
    session.flush()

    emb = _EmbeddingRepo(session, t.id).list()[0]
    chunk = session.get(Chunk, emb.chunk_id)
    section = session.get(Section, chunk.section_id)
    dv = session.get(DocumentVersion, section.document_version_id)
    doc = session.get(Document, dv.document_id)
    # embedding -> chunk -> section -> document_version -> document (FR16)
    assert doc.title == "Manual" and section.hierarchy_path == "3.2"
