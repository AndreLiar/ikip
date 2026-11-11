"""Eval corpus seeding (Story 5.1/5.2).

Pure: the corpus covers every evidence handle the gold references, and `resolve_gold_ids`
rewrites symbolic → real (leaving abstain cases empty). DB-gated: `seed_corpus` ingests the
docs through the real indexing path and returns a complete symbolic→chunk mapping.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest
from ikip_common.eval.seed import EVAL_CORPUS, resolve_gold_ids

_GOLD = Path(__file__).parent / "fixtures" / "gold" / "failure_modes.json"


# --- pure ------------------------------------------------------------------


def test_corpus_covers_every_gold_evidence_handle() -> None:
    gold = json.loads(_GOLD.read_text())
    referenced = {cid for c in gold["cases"] for cid in c.get("relevant_chunk_ids", [])}
    seeded = {d.symbolic_id for d in EVAL_CORPUS}
    assert referenced <= seeded, f"gold handles with no seed doc: {referenced - seeded}"


def test_resolve_gold_rewrites_handles_and_keeps_abstain_empty() -> None:
    gold = json.loads(_GOLD.read_text())
    mapping = {"c-e42": "11111111-1111-1111-1111-111111111111"}
    resolved = resolve_gold_ids(gold, mapping)
    assert resolved["gold_set_version"].endswith("-resolved")
    by_key = {c["case_key"]: c for c in resolved["cases"]}
    assert by_key["equipment-identifier-exact-fault-code"]["relevant_chunk_ids"] == [
        "11111111-1111-1111-1111-111111111111"
    ]
    # an abstain case has no evidence -> stays empty
    assert by_key["unanswerable-not-in-corpus"]["relevant_chunk_ids"] == []


# --- DB-gated --------------------------------------------------------------

_URL = os.environ.get("TEST_DATABASE_URL")
dbonly = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")


@dbonly
def test_seed_corpus_ingests_and_maps_all_handles() -> None:
    from ikip_common.db.base import Base
    from ikip_common.db.models import Chunk
    from ikip_common.eval.seed import seed_corpus
    from ikip_common.llm.fake import FakeEmbeddingClient
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    url = _URL.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    try:
        tenant_id = uuid.uuid4()
        with Session(engine) as s:
            mapping = seed_corpus(s, tenant_id, FakeEmbeddingClient())
            s.commit()
            # every seeded symbolic id resolved to a real chunk owned by the eval tenant
            assert {d.symbolic_id for d in EVAL_CORPUS} == set(mapping)
            n = s.execute(
                select(func.count()).select_from(Chunk).where(Chunk.tenant_id == tenant_id)
            ).scalar_one()
            assert n == len(EVAL_CORPUS)
            for chunk_id in mapping.values():
                assert s.get(Chunk, uuid.UUID(chunk_id)).tenant_id == tenant_id
    finally:
        Base.metadata.drop_all(engine)
