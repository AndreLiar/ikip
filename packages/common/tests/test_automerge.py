"""Stage-1 hierarchical auto-merge tests (ADR 0029).

`merge_section_window` is pure → tested without a DB. `expand_to_parents` reads sibling chunks
→ DB-backed, gated on TEST_DATABASE_URL (ephemeral Neon branch in CI; throwaway pg locally)."""

import os

import pytest
from ikip_common.llm.automerge import expand_to_parents, merge_section_window
from ikip_common.llm.hybrid import RetrievalOutcome
from langchain_core.documents import Document


# --- pure: merge_section_window -------------------------------------------------
def test_merge_whole_section_in_ordinal_order() -> None:
    sibs = [(2, "third"), (0, "first"), (1, "second")]  # deliberately unordered
    assert merge_section_window(0, sibs, max_tokens=100) == "first\n\nsecond\n\nthird"


def test_merge_empty_section() -> None:
    assert merge_section_window(0, [], max_tokens=100) == ""


def test_merge_windows_around_hit_when_over_budget() -> None:
    # 5 chunks of 40 chars; budget max_tokens=30 -> 120 chars fits ~2-3 chunks, not all 5.
    sibs = [(i, chr(ord("A") + i) * 40) for i in range(5)]
    out = merge_section_window(2, sibs, max_tokens=30)
    assert "C" * 40 in out  # the hit is always included
    assert "A" * 40 not in out  # far chunks dropped (windowed, not whole section)
    assert out.count("\n\n") < 4  # contiguous window, not the full section
    # window is contiguous (no gaps): every piece between first and last is present
    pieces = out.split("\n\n")
    letters = [p[0] for p in pieces]
    assert letters == sorted(letters) and all(
        ord(letters[i + 1]) - ord(letters[i]) == 1 for i in range(len(letters) - 1)
    )


def test_merge_hit_included_even_if_ordinal_missing() -> None:
    sibs = [(0, "a"), (1, "b")]
    assert merge_section_window(99, sibs, max_tokens=100) == "a\n\nb"  # fits → whole section


# --- DB-backed: expand_to_parents ----------------------------------------------
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


def _seed_section(session, contents):  # noqa: ANN001, ANN202
    from ikip_common.db.models import Chunk, DocumentVersion, Section, Tenant
    from ikip_common.db.models import Document as Doc

    t = Tenant(name="T")
    session.add(t)
    session.flush()
    d = Doc(tenant_id=t.id, title="Manual")
    session.add(d)
    session.flush()
    v = DocumentVersion(document_id=d.id, revision="A", checksum="chk", is_current=True)
    session.add(v)
    session.flush()
    sec = Section(document_version_id=v.id, heading="3. Procedure", hierarchy_path="3", ordinal=0)
    session.add(sec)
    session.flush()
    chunks = []
    for i, c in enumerate(contents):
        ch = Chunk(tenant_id=t.id, section_id=sec.id, content=c, chunk_metadata={"ordinal": i})
        session.add(ch)
        chunks.append(ch)
    session.flush()
    return t, sec, chunks


@dbtest
def test_expand_merges_section_and_keeps_child_citation(session) -> None:  # noqa: ANN001
    t, sec, chunks = _seed_section(session, ["alpha body", "beta body", "gamma body"])
    hit = chunks[1]
    doc = Document(
        page_content="beta body",
        metadata={"chunk_id": str(hit.id), "section_id": str(sec.id), "page_start": 7},
    )
    out = expand_to_parents(
        session, t.id, RetrievalOutcome(documents=[doc], abstained=False), parent_max_tokens=1000
    )
    assert len(out.documents) == 1
    # LLM now sees the whole parent section (in order) ...
    assert out.documents[0].page_content == "alpha body\n\nbeta body\n\ngamma body"
    # ... but the citation still points at the precise child chunk (FR16).
    assert out.documents[0].metadata["chunk_id"] == str(hit.id)
    assert out.documents[0].metadata["page_start"] == 7


@dbtest
def test_expand_dedups_multiple_hits_in_one_section(session) -> None:  # noqa: ANN001
    t, sec, chunks = _seed_section(session, ["a body", "b body", "c body"])
    d1 = Document(
        page_content="a body", metadata={"chunk_id": str(chunks[0].id), "section_id": str(sec.id)}
    )
    d2 = Document(
        page_content="c body", metadata={"chunk_id": str(chunks[2].id), "section_id": str(sec.id)}
    )
    out = expand_to_parents(
        session, t.id, RetrievalOutcome(documents=[d1, d2], abstained=False), parent_max_tokens=1000
    )
    assert len(out.documents) == 1  # both hits collapse to one parent
    assert out.documents[0].metadata["chunk_id"] == str(chunks[0].id)  # best-ranked kept


@dbtest
def test_expand_passes_through_abstention(session) -> None:  # noqa: ANN001
    t, _, _ = _seed_section(session, ["x body"])
    out = expand_to_parents(session, t.id, RetrievalOutcome(documents=[], abstained=True))
    assert out.abstained is True and out.documents == []
