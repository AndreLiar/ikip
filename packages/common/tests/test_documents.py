"""Document dedup + versioning tests (Story 2.5). DB-backed → gated on
TEST_DATABASE_URL (ephemeral Neon branch in CI). flush+rollback."""

import os

import pytest
from ikip_common.db.base import Base
from ikip_common.db.documents import DocumentRepository, DuplicateDocumentError
from ikip_common.db.models import DocumentVersion, Tenant
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


def _repo(session: Session) -> DocumentRepository:
    t = Tenant(name="T")
    session.add(t)
    session.flush()
    return DocumentRepository(session, t.id)


def test_new_document_creates_version(session: Session) -> None:
    repo = _repo(session)
    out = repo.ingest_version(title="Manual", checksum="c1", fingerprint="0" * 16, revision="A")
    assert out.created_document is True
    assert out.version.is_current is True
    assert out.version.revision == "A"


def test_exact_duplicate_rejected(session: Session) -> None:
    repo = _repo(session)
    repo.ingest_version(title="Manual", checksum="dup", fingerprint="0" * 16, revision="A")
    session.flush()
    with pytest.raises(DuplicateDocumentError):
        repo.ingest_version(
            title="Manual again", checksum="dup", fingerprint="f" * 16, revision="B"
        )


def test_near_duplicate_becomes_new_version_superseding(session: Session) -> None:
    repo = _repo(session)
    fp1 = "0000000000000000"
    fp2 = "0000000000000001"  # Hamming distance 1 -> near duplicate
    out1 = repo.ingest_version(title="Doc", checksum="v1", fingerprint=fp1, revision="A")
    session.flush()
    out2 = repo.ingest_version(title="Doc", checksum="v2", fingerprint=fp2, revision="B")
    session.flush()

    assert out2.created_document is False  # same document, new version
    assert out2.document.id == out1.document.id

    # supersession: version A no longer current, B is — A is NOT deleted (NFR15)
    versions = (
        session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == out1.document.id)
            .order_by(DocumentVersion.revision)
        )
        .scalars()
        .all()
    )
    assert len(versions) == 2  # both kept
    current = {v.revision: v.is_current for v in versions}
    assert current == {"A": False, "B": True}


def test_unrelated_content_creates_separate_document(session: Session) -> None:
    repo = _repo(session)
    repo.ingest_version(title="A", checksum="a", fingerprint="0000000000000000", revision="A")
    session.flush()
    out = repo.ingest_version(title="B", checksum="b", fingerprint="ffffffffffffffff", revision="A")
    assert out.created_document is True  # far fingerprint -> new document


def test_dedup_is_tenant_scoped(session: Session) -> None:
    repo_a = _repo(session)
    repo_b = _repo(session)
    repo_a.ingest_version(title="X", checksum="same", fingerprint="0" * 16, revision="A")
    session.flush()
    # same checksum in another tenant is NOT a duplicate (isolation)
    out = repo_b.ingest_version(title="X", checksum="same", fingerprint="0" * 16, revision="A")
    assert out.created_document is True
