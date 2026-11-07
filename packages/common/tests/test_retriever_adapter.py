"""IkipRetriever (LangChain BaseRetriever adapter) tests (Story 3.3, ADR 0021).

The adapter is the single place LangChain enters the read path. Skipped entirely
when langchain_core is absent (the fast CI `validate` job without the `embeddings`
group). Pure part: SearchHit -> Document citation mapping. DB part: the retriever
returns LangChain Documents backed by our tenant-scoped SQL, citations in metadata.
"""

import os
import uuid

import pytest

pytest.importorskip("langchain_core")

from ikip_common.db.retrieval import SearchHit  # noqa: E402
from ikip_common.llm.retriever import IkipRetriever, hit_to_document  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


def _bare_session() -> Session:
    # A real Session instance (no bind) — satisfies pydantic's isinstance check;
    # arm validation raises before any query touches it.
    return Session()


def _hit(**over) -> SearchHit:
    base = {
        "chunk_id": uuid.uuid4(),
        "content": "Fault E42 pump motor overheat.",
        "score": 0.87,
        "document_id": uuid.uuid4(),
        "document_version_id": uuid.uuid4(),
        "revision": "B",
        "is_current": True,
        "section_id": uuid.uuid4(),
        "heading": "3.2 Faults",
        "hierarchy_path": "3.2",
        "page_start": 142,
        "page_end": 143,
    }
    base.update(over)
    return SearchHit(**base)


def test_hit_to_document_preserves_citation_in_metadata() -> None:
    hit = _hit()
    doc = hit_to_document(hit)
    assert doc.page_content == hit.content
    m = doc.metadata
    assert m["revision"] == "B" and m["hierarchy_path"] == "3.2"
    assert m["page_start"] == 142 and m["page_end"] == 143
    assert m["score"] == 0.87
    # ids are stringified for JSON-friendly metadata
    assert m["chunk_id"] == str(hit.chunk_id)
    assert m["document_version_id"] == str(hit.document_version_id)


def test_vector_arm_requires_embedding_client() -> None:
    r = IkipRetriever(session=_bare_session(), tenant_id=uuid.uuid4(), arm="vector")
    with pytest.raises(ValueError, match="embedding_client"):
        r._search("query")


def test_unknown_arm_rejected() -> None:
    r = IkipRetriever(session=_bare_session(), tenant_id=uuid.uuid4(), arm="bogus")
    with pytest.raises(ValueError, match="unknown arm"):
        r._search("query")


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


@dbonly
def test_retriever_lexical_returns_documents(engine) -> None:
    from ikip_common.db.embeddings import embed_and_store
    from ikip_common.db.models import Chunk, Document, DocumentVersion, Section, Tenant
    from ikip_common.llm import FakeEmbeddingClient
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        t = Tenant(name="A")
        session.add(t)
        session.flush()
        d = Document(tenant_id=t.id, title="Manual")
        session.add(d)
        session.flush()
        dv = DocumentVersion(document_id=d.id, revision="A", checksum=f"c-{uuid.uuid4()}")
        session.add(dv)
        session.flush()
        sec = Section(document_version_id=dv.id, heading="3.2", hierarchy_path="3.2")
        session.add(sec)
        session.flush()
        ch = Chunk(tenant_id=t.id, section_id=sec.id, content="Fault E42 pump motor overheat.")
        session.add(ch)
        session.flush()
        client = FakeEmbeddingClient(dimensions=512)
        embed_and_store(session, t.id, client, [ch])
        session.flush()

        lexical = IkipRetriever(session=session, tenant_id=t.id, arm="lexical")
        docs = lexical.invoke("E42")
        assert len(docs) == 1
        assert docs[0].metadata["hierarchy_path"] == "3.2"

        vector = IkipRetriever(
            session=session, tenant_id=t.id, arm="vector", embedding_client=client
        )
        vdocs = vector.invoke("pump overheating")
        assert len(vdocs) == 1
        assert vdocs[0].metadata["chunk_id"] == str(ch.id)
        session.rollback()
