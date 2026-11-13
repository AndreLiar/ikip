"""Adversarial tenant-isolation + object-level ACL — SQL layer (Story 6.2) — DB-gated.

Proves at the real-Postgres layer what the hermetic API tests assert at the edge:
  - cross-tenant retrieval (lexical + vector) returns ZERO of another tenant's chunks (AC1);
  - object-level permissions are enforced on CHUNKS, not just documents: a restricted doc's
    chunks are excluded for a non-permitted user, included for a direct- or workspace-ACL
    user; a doc with no ACL rows is tenant-public (AC4);
  - a document version of tenant B is not resolvable under tenant A (source access, AC1).
Runs on the ephemeral Neon branch in the `db-tests` job.
"""

from __future__ import annotations

import os
import uuid

import pytest
from ikip_common.db.base import Base
from ikip_common.db.embeddings import embed_and_store
from ikip_common.db.models import (
    AppUser,
    Chunk,
    Document,
    DocumentPermission,
    DocumentVersion,
    Section,
    Tenant,
    UserRole,
    Workspace,
    WorkspaceMembership,
)
from ikip_common.db.retrieval import RetrievalFilters, lexical_search, vector_search
from ikip_common.llm import FakeEmbeddingClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

_URL = os.environ.get("TEST_DATABASE_URL")
dbonly = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")
pytestmark = dbonly


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


def _user(session: Session, tenant: Tenant) -> AppUser:
    u = AppUser(tenant_id=tenant.id, email=f"{uuid.uuid4()}@x", role=UserRole.technician)
    session.add(u)
    session.flush()
    return u


def _doc_with_chunk(session: Session, tenant: Tenant, content: str) -> tuple[Document, Chunk]:
    d = Document(tenant_id=tenant.id, title="Manual")
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
    return d, ch


# --- cross-tenant retrieval (AC1) ------------------------------------------


def test_lexical_and_vector_retrieval_never_cross_tenant(session: Session) -> None:
    a, b = Tenant(name="A"), Tenant(name="B")
    session.add_all([a, b])
    session.flush()
    # identical content in BOTH tenants
    _, a_chunk = _doc_with_chunk(session, a, "Fault E42 pump overheat")
    _, b_chunk = _doc_with_chunk(session, b, "Fault E42 pump overheat")
    emb = FakeEmbeddingClient(dimensions=8)
    for t in (a, b):  # embed both tenants' chunks
        chunks = list(session.execute(_tenant_chunks(t.id)).scalars())
        embed_and_store(session, t.id, emb, chunks)
    session.flush()

    # tenant A's search returns A's chunk and NEVER B's identical one
    lex_ids = {h.chunk_id for h in lexical_search(session, a.id, "E42", limit=10)}
    assert a_chunk.id in lex_ids and b_chunk.id not in lex_ids

    qvec = emb.embed(["Fault E42"])[0]
    vec_ids = {
        h.chunk_id
        for h in vector_search(session, a.id, qvec, model_version=emb.model_version, limit=10)
    }
    assert b_chunk.id not in vec_ids  # cross-tenant vector leak would put B's id here


def _tenant_chunks(tenant_id: uuid.UUID):
    from sqlalchemy import select

    return select(Chunk).where(Chunk.tenant_id == tenant_id)


# --- object-level ACL on chunks (AC4) --------------------------------------


def test_object_level_acl_excludes_restricted_doc_chunks(session: Session) -> None:
    t = Tenant(name="A")
    session.add(t)
    session.flush()
    permitted = _user(session, t)
    other = _user(session, t)

    # a PUBLIC doc (no ACL rows) and a RESTRICTED doc (ACL -> permitted only)
    _doc_with_chunk(session, t, "public lubrication schedule E42")
    restricted_doc, restricted_chunk = _doc_with_chunk(session, t, "restricted torque spec E42")
    session.add(
        DocumentPermission(tenant_id=t.id, document_id=restricted_doc.id, user_id=permitted.id)
    )
    session.flush()

    # non-permitted user: restricted chunk EXCLUDED, public chunk visible
    seen_other = {
        h.chunk_id for h in lexical_search(session, t.id, "E42", filters=_acl(other), limit=10)
    }
    assert restricted_chunk.id not in seen_other
    assert seen_other  # still sees the public doc

    # permitted user (direct ACL): restricted chunk INCLUDED
    seen_permitted = {
        h.chunk_id for h in lexical_search(session, t.id, "E42", filters=_acl(permitted), limit=10)
    }
    assert restricted_chunk.id in seen_permitted


def test_object_level_acl_grants_via_workspace(session: Session) -> None:
    t = Tenant(name="A")
    session.add(t)
    session.flush()
    member = _user(session, t)
    ws = Workspace(tenant_id=t.id, name="maintenance")
    session.add(ws)
    session.flush()
    session.add(
        WorkspaceMembership(workspace_id=ws.id, user_id=member.id, role=UserRole.technician)
    )
    doc, chunk = _doc_with_chunk(session, t, "workspace torque spec E42")
    session.add(DocumentPermission(tenant_id=t.id, document_id=doc.id, workspace_id=ws.id))
    session.flush()

    hits = lexical_search(session, t.id, "E42", filters=_acl(member), limit=10)
    assert chunk.id in {h.chunk_id for h in hits}  # workspace membership grants access (AC4)


def _acl(user: AppUser) -> RetrievalFilters:
    return RetrievalFilters(user_id=user.id)


# --- source access cross-tenant (AC1) --------------------------------------


def test_source_version_not_resolvable_across_tenant(session: Session) -> None:
    from sqlalchemy import select

    a, b = Tenant(name="A"), Tenant(name="B")
    session.add_all([a, b])
    session.flush()
    b_doc, _ = _doc_with_chunk(session, b, "secret")
    b_version = session.execute(
        select(DocumentVersion.id).where(DocumentVersion.document_id == b_doc.id)
    ).scalar_one()

    # the source-url authorization query (version ∈ tenant) — tenant A must NOT resolve B's version
    def resolvable(tenant_id: uuid.UUID) -> bool:
        stmt = (
            select(DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(DocumentVersion.id == b_version, Document.tenant_id == tenant_id)
        )
        return session.execute(stmt).scalar_one_or_none() is not None

    assert resolvable(b.id) is True
    assert resolvable(a.id) is False  # cross-tenant source access denied
