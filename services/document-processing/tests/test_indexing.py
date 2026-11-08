"""Build-time indexing (Epic 2↔3): chunk → persist Section/Chunk → embed.

Pure part (CI): section planning. DB part (gated on TEST_DATABASE_URL): the closed
loop — index curated text, then retrieval (lexical + vector) actually finds the chunk
with citations. Uses FakeEmbeddingClient (no network). Langchain-free.
"""

import os
import uuid

import pytest
from ikip_docproc.chunking import ChunkSpec
from ikip_docproc.indexing import index_version, plan_sections

# --- pure: section planning -----------------------------------------------


def test_plan_sections_groups_by_path_in_order() -> None:
    specs = [
        ChunkSpec(content="a", section_path="1", section_heading="Intro", ordinal=0),
        ChunkSpec(content="b", section_path="1", section_heading="Intro", ordinal=1),
        ChunkSpec(content="c", section_path="3.2", section_heading="Faults", ordinal=2),
    ]
    sections = plan_sections(specs)
    assert [s.path for s in sections] == ["1", "3.2"]
    assert [s.ordinal for s in sections] == [0, 1]
    assert len(sections[0].specs) == 2 and sections[1].heading == "Faults"


def test_layout_regions_plan_page_sections() -> None:
    from ikip_docproc.chunking import chunk_regions

    specs = chunk_regions([{"page": 9, "text": "Reset fault E42", "bbox": [0.2, 0.3, 0.7, 0.4]}])
    sections = plan_sections(specs)
    assert sections[0].path == "page-9"
    assert specs[0].regions[0]["bbox"] == [0.2, 0.3, 0.7, 0.4]


# --- DB-backed closed loop -------------------------------------------------

_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark_db = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")


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


def _version(session):
    from ikip_common.db.models import Document, DocumentVersion, Tenant

    t = Tenant(name="A")
    session.add(t)
    session.flush()
    d = Document(tenant_id=t.id, title="Pump Manual")
    session.add(d)
    session.flush()
    dv = DocumentVersion(document_id=d.id, revision="A", checksum=f"c-{uuid.uuid4()}")
    session.add(dv)
    session.flush()
    return t, dv


@pytestmark_db
def test_index_version_populates_and_is_retrievable(session) -> None:
    from ikip_common.db.models import Chunk, Embedding, Section
    from ikip_common.db.retrieval import lexical_search, vector_search
    from ikip_common.llm import FakeEmbeddingClient
    from sqlalchemy import func, select

    t, dv = _version(session)
    client = FakeEmbeddingClient(dimensions=512)
    text = "Fault code E42 indicates the pump motor has overheated. Stop the pump and inspect."

    report = index_version(session, t.id, dv.id, text, client)
    session.flush()

    assert report.sections_created >= 1 and report.chunks_created >= 1
    assert report.embed.embedded == report.chunks_created
    # rows persisted
    assert session.execute(select(func.count()).select_from(Section)).scalar_one() >= 1
    n_chunks = session.execute(select(func.count()).select_from(Chunk)).scalar_one()
    n_emb = session.execute(select(func.count()).select_from(Embedding)).scalar_one()
    assert n_chunks == n_emb >= 1

    # closed loop: retrieval now finds the indexed content, with citations (FR16)
    lex = lexical_search(session, t.id, "E42", limit=5)
    assert lex and lex[0].revision == "A" and lex[0].document_version_id == dv.id
    [qvec] = client.embed(["pump overheating"])
    vec = vector_search(session, t.id, qvec, model_version=client.model_version, limit=5)
    assert vec and vec[0].chunk_id == lex[0].chunk_id


@pytestmark_db
def test_index_version_is_idempotent(session) -> None:
    from ikip_common.db.models import Chunk
    from ikip_common.llm import FakeEmbeddingClient
    from sqlalchemy import func, select

    t, dv = _version(session)
    client = FakeEmbeddingClient(dimensions=512)
    text = "Fault E42: pump motor overheat. Inspect bearings."

    first = index_version(session, t.id, dv.id, text, client)
    session.flush()
    n_after_first = session.execute(select(func.count()).select_from(Chunk)).scalar_one()

    second = index_version(session, t.id, dv.id, text, client)
    session.flush()
    n_after_second = session.execute(select(func.count()).select_from(Chunk)).scalar_one()

    assert first.chunks_created >= 1
    assert second.sections_created == 0 and second.chunks_created == 0  # no duplicates
    assert n_after_first == n_after_second  # re-index didn't add chunks
