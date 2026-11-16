"""Caption-and-embed + visual-citation + visual-eval tests (Epic 9, Story 9.2, ADR 0031).

Pure: citation resolution, region-recall, captioner port. DB-backed: caption→chunk indexing."""

import os

import pytest
from ikip_common.eval.visual_eval import (
    visual_elements_from_hits,
    visual_region_recall_at_k,
)
from ikip_common.vision import FakeVisionCaptioner, VisionCaptioner
from ikip_common.visual_caption import visual_citation_from_chunk_metadata


# --- pure ---------------------------------------------------------------------
def test_fake_captioner_satisfies_port_and_varies_by_kind() -> None:
    cap = FakeVisionCaptioner("a diagram", by_kind={"table": "a data table"})
    assert isinstance(cap, VisionCaptioner)
    assert cap.caption(b"x", kind="table") == "a data table"
    assert cap.caption(b"x", kind="figure") == "a diagram"


def test_visual_citation_resolves_only_visual_chunks() -> None:
    meta = {
        "is_visual": True,
        "visual_element_id": "ve1",
        "kind": "figure",
        "page": 7,
        "bbox": [0.1, 0.2, 0.8, 0.5],
        "crop_object_key": "crops/ve1.png",
    }
    cit = visual_citation_from_chunk_metadata(meta)
    assert cit.visual_element_id == "ve1" and cit.page == 7 and cit.kind == "figure"
    assert cit.bbox == [0.1, 0.2, 0.8, 0.5] and cit.crop_object_key == "crops/ve1.png"
    assert visual_citation_from_chunk_metadata({"is_visual": False}) is None  # text chunk
    assert visual_citation_from_chunk_metadata({}) is None


def test_region_recall_and_hit_extraction() -> None:
    hits = [
        {"is_visual": True, "visual_element_id": "a"},
        {"is_visual": False},  # a text chunk, ignored
        {"is_visual": True, "visual_element_id": "b"},
    ]
    ids = visual_elements_from_hits(hits)
    assert ids == ["a", "b"]  # order preserved, text chunk skipped
    assert visual_region_recall_at_k(ids, ["b"], 5) == 1.0
    assert visual_region_recall_at_k(ids, ["c"], 5) == 0.0
    assert visual_region_recall_at_k(ids, ["a", "b"], 1) == 0.5  # only top-1 counted


# --- DB-backed: caption → searchable chunk ------------------------------------
_URL = os.environ.get("TEST_DATABASE_URL")
dbtest = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")


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


def _seed_version_with_section(session, tenant):  # noqa: ANN001, ANN202
    from ikip_common.db.models import Document, DocumentVersion, Section

    d = Document(tenant_id=tenant, title="Manual")
    session.add(d)
    session.flush()
    v = DocumentVersion(document_id=d.id, revision="A", checksum="c", is_current=True)
    session.add(v)
    session.flush()
    sec = Section(document_version_id=v.id, heading="3. Wiring", hierarchy_path="3", ordinal=0)
    session.add(sec)
    session.flush()
    return v.id, sec.id


def _tenant(session):  # noqa: ANN001, ANN202
    from ikip_common.db.models import Tenant

    t = Tenant(name="T")
    session.add(t)
    session.flush()
    return t.id


@dbtest
def test_caption_creates_searchable_chunk_linked_to_region(session) -> None:  # noqa: ANN001
    from ikip_common.db.models import Chunk, VisualElement
    from ikip_common.visual_caption import caption_and_index_visual_elements
    from sqlalchemy import select

    t = _tenant(session)
    v, sec = _seed_version_with_section(session, t)
    el = VisualElement(
        tenant_id=t,
        document_version_id=v,
        section_id=sec,
        kind="schematic",
        page=12,
        bbox=[0.1, 0.1, 0.9, 0.6],
        confidence=0.9,
        low_confidence=False,
        crop_object_key="crops/el.png",
    )
    session.add(el)
    session.flush()

    n = caption_and_index_visual_elements(
        session,
        t,
        v,
        FakeVisionCaptioner("wiring schematic: E42 fault reset, relay K3"),
        load_image=lambda _el: b"PNGBYTES",
    )
    session.flush()
    assert n == 1

    # the element is captioned, and a SEARCHABLE chunk now carries that caption + the region link
    assert session.get(VisualElement, el.id).caption.startswith("wiring schematic")
    chunk = session.execute(
        select(Chunk).where(Chunk.tenant_id == t, Chunk.section_id == sec)
    ).scalar_one()
    assert chunk.content.startswith("wiring schematic")  # the embedded/searched text
    assert chunk.page_start == 12
    assert chunk.chunk_metadata["is_visual"] is True
    assert chunk.chunk_metadata["visual_element_id"] == str(el.id)  # hit -> region

    # and a retrieval hit on that chunk resolves to the visual region
    cit = visual_citation_from_chunk_metadata(chunk.chunk_metadata)
    assert cit.visual_element_id == str(el.id) and cit.page == 12 and cit.kind == "schematic"


@dbtest
def test_captioning_is_idempotent_and_skips_sectionless(session) -> None:  # noqa: ANN001
    from ikip_common.db.models import VisualElement
    from ikip_common.visual_caption import caption_and_index_visual_elements

    t = _tenant(session)
    v, sec = _seed_version_with_section(session, t)
    session.add(
        VisualElement(
            tenant_id=t,
            document_version_id=v,
            section_id=sec,
            kind="figure",
            page=1,
            bbox=None,
            confidence=0.9,
            low_confidence=False,
        )
    )
    session.add(
        VisualElement(  # no section -> skipped (can't attach a searchable chunk)
            tenant_id=t,
            document_version_id=v,
            section_id=None,
            kind="figure",
            page=2,
            bbox=None,
            confidence=0.9,
            low_confidence=False,
        )
    )
    session.flush()
    cap = FakeVisionCaptioner("x")
    first = caption_and_index_visual_elements(session, t, v, cap, lambda _e: b"img")
    session.flush()
    second = caption_and_index_visual_elements(session, t, v, cap, lambda _e: b"img")
    assert first == 1  # only the sectioned element captioned
    assert second == 0  # already captioned -> nothing re-done
