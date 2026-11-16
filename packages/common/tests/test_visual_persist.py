"""VisualElement persistence + linkage tests (Epic 9, Story 9.1, ADR 0031). DB-backed."""

import os

import pytest
from ikip_common.db.visual import persist_visual_elements

_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")


class _Spec:
    def __init__(self, kind, page, bbox, confidence, low):  # noqa: ANN001
        self.kind, self.page, self.bbox = kind, page, bbox
        self.confidence, self.low_confidence = confidence, low


@pytest.fixture(scope="module")
def engine():  # noqa: ANN201
    from ikip_common.db.base import Base
    from sqlalchemy import create_engine

    url = _URL.replace("postgresql://", "postgresql+psycopg://", 1) if _URL else _URL
    eng = create_engine(url)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def session(engine):  # noqa: ANN001, ANN201
    from sqlalchemy.orm import Session

    with Session(engine) as s:
        yield s
        s.rollback()


def _version(session, tenant):  # noqa: ANN001, ANN202
    from ikip_common.db.models import Document, DocumentVersion

    d = Document(tenant_id=tenant, title="Manual")
    session.add(d)
    session.flush()
    v = DocumentVersion(document_id=d.id, revision="A", checksum="c", is_current=True)
    session.add(v)
    session.flush()
    return v.id


def _tenant(session):  # noqa: ANN001, ANN202
    from ikip_common.db.models import Tenant

    t = Tenant(name="T")
    session.add(t)
    session.flush()
    return t.id


def test_persists_with_region_and_links_to_version(session) -> None:
    from ikip_common.db.models import VisualElement
    from sqlalchemy import select

    t = _tenant(session)
    v = _version(session, t)
    specs = [
        _Spec("table", 7, (0.1, 0.1, 0.5, 0.4), 0.9, False),
        _Spec("figure", 7, (0.2, 0.5, 0.8, 0.9), 0.4, True),  # low-confidence
    ]
    n = persist_visual_elements(session, t, v, specs)
    session.flush()
    assert n == 2
    rows = (
        session.execute(select(VisualElement).where(VisualElement.tenant_id == t)).scalars().all()
    )
    assert {r.kind for r in rows} == {"table", "figure"}
    fig = next(r for r in rows if r.kind == "figure")
    assert fig.document_version_id == v  # linked back-reference (AC2)
    assert fig.page == 7 and fig.bbox == [0.2, 0.5, 0.8, 0.9]  # page + region (FR16)
    assert fig.low_confidence is True  # flagged (AC3)


def test_low_confidence_is_queryable_for_review(session) -> None:
    from ikip_common.db.models import VisualElement
    from sqlalchemy import select

    t = _tenant(session)
    v = _version(session, t)
    persist_visual_elements(
        session,
        t,
        v,
        [_Spec("figure", 1, None, 0.3, True), _Spec("table", 1, None, 0.9, False)],
    )
    session.flush()
    flagged = (
        session.execute(
            select(VisualElement).where(
                VisualElement.tenant_id == t, VisualElement.low_confidence.is_(True)
            )
        )
        .scalars()
        .all()
    )
    assert len(flagged) == 1 and flagged[0].kind == "figure"


def test_cascades_on_version_delete(session) -> None:
    from ikip_common.db.models import Document, DocumentVersion, VisualElement
    from sqlalchemy import func, select

    t = _tenant(session)
    v = _version(session, t)
    persist_visual_elements(session, t, v, [_Spec("figure", 1, None, 0.9, False)])
    session.flush()
    # deleting the version removes its visual elements (no orphans)
    doc_id = session.execute(
        select(DocumentVersion.document_id).where(DocumentVersion.id == v)
    ).scalar_one()
    session.delete(session.get(Document, doc_id))
    session.flush()
    assert session.execute(select(func.count()).select_from(VisualElement)).scalar() == 0
