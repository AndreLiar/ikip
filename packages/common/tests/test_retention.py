"""Retention, deletion & provenance (Story 6.5). Pure (license/provenance) + DB-gated."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from ikip_common.db.models import Document, DocumentVersion
from ikip_common.db.retention import (
    is_license_allowed,
    provenance,
)

# --- pure: licensing gate + provenance -------------------------------------


def test_license_gate_allows_known_and_rejects_unknown_or_empty() -> None:
    assert is_license_allowed("CC-BY") is True
    assert is_license_allowed("manufacturer-authorized") is True
    assert is_license_allowed("licence-ouverte") is True  # Etalab (FR open data)
    assert is_license_allowed("Licence-Ouverte") is True  # case-insensitive
    assert is_license_allowed("proprietary-no-reuse") is False
    assert is_license_allowed(None) is False
    assert is_license_allowed("") is False


def test_provenance_reports_source_and_per_version() -> None:
    d = Document(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), title="M", source="oem.com", rights="CC-BY"
    )
    vs = [
        DocumentVersion(document_id=d.id, revision="A", checksum="h1", is_current=False),
        DocumentVersion(
            document_id=d.id,
            revision="B",
            checksum="h2",
            is_current=True,
            source_object_key="raw/b",
        ),
    ]
    p = provenance(d, vs)
    assert p["source"] == "oem.com" and p["license"] == "CC-BY" and p["license_allowed"] is True
    assert [v["revision"] for v in p["versions"]] == ["A", "B"]
    assert p["versions"][1]["source_object_key"] == "raw/b"


# --- DB-gated: deletion + retention ----------------------------------------

_URL = os.environ.get("TEST_DATABASE_URL")
dbonly = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")


class _RecordingStorage:
    """Minimal ObjectStorage: records deletes (and can simulate a failure)."""

    def __init__(self, fail: set[str] | None = None) -> None:
        self.deleted: list[str] = []
        self._fail = fail or set()

    def put(self, key, data, *, content_type=None):  # noqa: ANN001, ANN201
        return key

    def get(self, key):  # noqa: ANN001, ANN201
        return b""

    def exists(self, key) -> bool:  # noqa: ANN001
        return True

    def presigned_url(self, key, *, expires_s=3600) -> str:  # noqa: ANN001
        return f"https://x/{key}"

    def delete(self, key) -> None:  # noqa: ANN001
        if key in self._fail:
            raise RuntimeError("storage down")
        self.deleted.append(key)


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


@pytest.fixture
def session(engine):
    from sqlalchemy.orm import Session

    with Session(engine) as s:
        yield s
        s.rollback()


def _seed_document(session, tenant_id, *, created_at=None, keys=True):  # noqa: ANN001, ANN202
    from ikip_common.db.embeddings import embed_and_store
    from ikip_common.db.models import Chunk, Section, Tenant
    from ikip_common.llm import FakeEmbeddingClient

    if session.get(Tenant, tenant_id) is None:
        session.add(Tenant(id=tenant_id, name="T"))
        session.flush()
    d = Document(tenant_id=tenant_id, title="Manual", source="oem.com", rights="CC-BY")
    if created_at:
        d.created_at = created_at
    session.add(d)
    session.flush()
    dv = DocumentVersion(
        document_id=d.id,
        revision="A",
        checksum=f"h-{uuid.uuid4()}",
        curated_object_key="curated/a" if keys else None,
        source_object_key="raw/a" if keys else None,
    )
    session.add(dv)
    session.flush()
    sec = Section(document_version_id=dv.id, heading="3.2", hierarchy_path="3.2")
    session.add(sec)
    session.flush()
    ch = Chunk(tenant_id=tenant_id, section_id=sec.id, content="Fault E42")
    session.add(ch)
    session.flush()
    embed_and_store(session, tenant_id, FakeEmbeddingClient(), [ch])
    session.flush()
    return d


@dbonly
def test_delete_document_removes_all_stores_and_audits(session) -> None:
    from ikip_common.db.models import AuditEvent, Chunk, Embedding
    from ikip_common.db.retention import delete_document
    from sqlalchemy import func, select

    tenant = uuid.uuid4()
    d = _seed_document(session, tenant)
    storage = _RecordingStorage()

    report = delete_document(session, storage, tenant, d.id)

    assert report.versions == 1 and report.chunks == 1 and report.embeddings == 1
    assert set(storage.deleted) == {"curated/a", "raw/a"}  # object stores cleared
    # DB cascade removed everything
    assert session.get(Document, d.id) is None
    assert session.execute(select(func.count()).select_from(Chunk)).scalar_one() == 0
    assert session.execute(select(func.count()).select_from(Embedding)).scalar_one() == 0
    # audit-logged (AC4)
    audit = session.execute(
        select(AuditEvent).where(AuditEvent.operation == "data.delete")
    ).scalar_one()
    assert audit.resource_id == d.id and audit.tenant_id == tenant


@dbonly
def test_delete_is_tenant_scoped(session) -> None:
    from ikip_common.db.retention import delete_document

    owner, attacker = uuid.uuid4(), uuid.uuid4()
    d = _seed_document(session, owner)
    with pytest.raises(ValueError, match="not found"):
        delete_document(session, _RecordingStorage(), attacker, d.id)  # cross-tenant delete denied


@dbonly
def test_retention_sweep_deletes_only_stale(session) -> None:
    from ikip_common.db.models import Tenant
    from ikip_common.db.retention import retention_sweep

    tenant = uuid.uuid4()
    old = _seed_document(session, tenant, created_at=datetime.now(UTC) - timedelta(days=400))
    fresh = _seed_document(session, tenant, created_at=datetime.now(UTC))
    session.get(Tenant, tenant).policies = {"retention_days": 365}
    session.flush()

    reports = retention_sweep(session, _RecordingStorage(), tenant)
    assert [r.document_id for r in reports] == [str(old.id)]
    assert session.get(Document, old.id) is None
    assert session.get(Document, fresh.id) is not None  # within window -> kept
