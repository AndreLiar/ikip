"""Section/Chunk persistence + citation back-reference tests (Story 3.1 AC1/AC3).
DB-backed → gated on TEST_DATABASE_URL (ephemeral Neon branch in CI)."""

import os

import pytest
from ikip_common.db.base import Base
from ikip_common.db.models import (
    Chunk,
    Document,
    DocumentVersion,
    Section,
    Tenant,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture(scope="module")
def engine():
    url = _URL.replace("postgresql://", "postgresql+psycopg://", 1) if _URL else _URL
    eng = create_engine(url)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s
        s.rollback()


def _doc_version(session: Session) -> tuple[Tenant, DocumentVersion]:
    t = Tenant(name="T")
    session.add(t)
    session.flush()
    d = Document(tenant_id=t.id, title="Manual")
    session.add(d)
    session.flush()
    dv = DocumentVersion(document_id=d.id, revision="A", checksum="c1")
    session.add(dv)
    session.flush()
    return t, dv


def test_chunk_resolves_back_to_document_version_page_section(session: Session) -> None:
    t, dv = _doc_version(session)
    sec = Section(
        document_version_id=dv.id,
        heading="3.2 Fault Handling",
        hierarchy_path="3.2",
        page_start=142,
        page_end=143,
    )
    session.add(sec)
    session.flush()
    chunk = Chunk(
        tenant_id=t.id,
        section_id=sec.id,
        content="Reset E42...",
        page_start=142,
        page_end=142,
        token_count=12,
    )
    session.add(chunk)
    session.flush()

    # Walk the citation chain: chunk -> section -> document_version (FR16)
    loaded = session.execute(select(Chunk).where(Chunk.id == chunk.id)).scalar_one()
    assert loaded.page_start == 142
    assert loaded.section_id == sec.id
    loaded_sec = session.execute(
        select(Section).where(Section.id == loaded.section_id)
    ).scalar_one()
    assert loaded_sec.document_version_id == dv.id
    assert loaded_sec.hierarchy_path == "3.2"


def test_chunk_is_tenant_scoped(session: Session) -> None:
    t, dv = _doc_version(session)
    sec = Section(document_version_id=dv.id)
    session.add(sec)
    session.flush()
    session.add(Chunk(tenant_id=t.id, section_id=sec.id, content="x"))
    session.flush()
    # another tenant sees no chunks
    other = Tenant(name="Other")
    session.add(other)
    session.flush()
    rows = session.execute(select(Chunk).where(Chunk.tenant_id == other.id)).scalars().all()
    assert rows == []


def test_section_hierarchy_parent(session: Session) -> None:
    _, dv = _doc_version(session)
    parent = Section(document_version_id=dv.id, heading="3 Maintenance", hierarchy_path="3")
    session.add(parent)
    session.flush()
    child = Section(
        document_version_id=dv.id,
        parent_section_id=parent.id,
        heading="3.2 Fault Handling",
        hierarchy_path="3.2",
    )
    session.add(child)
    session.flush()
    assert child.parent_section_id == parent.id
