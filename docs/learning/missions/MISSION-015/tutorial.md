# MISSION-015 — Reproduction tutorial

Fuse the two arms, rerank, filter, abstain. Concept: [hybrid-retrieval](../../concepts/hybrid-retrieval.md);
decision [ADR 0021](../../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md).

## Prerequisites
- Stories 3.2–3.3 done. `uv sync --group embeddings`. Postgres+pgvector for DB tests.
- No new migration (filters reuse existing columns).

## Hybrid retrieve (Python)
```python
from ikip_common.llm.hybrid import hybrid_retrieve
from ikip_common.db import RetrievalFilters
from ikip_common.llm import build_embedding_client

client = build_embedding_client()
outcome = hybrid_retrieve(
    session, tenant_id, "pump E42 overheat", client,
    filters=RetrievalFilters(current_only=True, document_type="manual",
                             metadata={"equipment_model": "P-200"}),
    lexical_min_score=0.0, vector_min_score=0.2,
)
if outcome.abstained:
    print("insufficient evidence")        # safety path (AC4)
else:
    for d in outcome.documents:            # langchain_core Documents, citations in metadata
        print(d.metadata["revision"], d.metadata["hierarchy_path"], d.metadata["rrf_score"])
```

## Plug a real reranker later (the port)
```python
class MyCrossEncoder:                       # implements the Reranker Protocol
    def rerank(self, query, documents, *, top_k=None):
        ...                                 # reorder by a cross-encoder / Cohere score
hybrid_retrieve(..., reranker=MyCrossEncoder())
```

## RRF intuition (pure, no DB)
```python
from ikip_common.llm.hybrid import reciprocal_rank_fusion
from langchain_core.documents import Document
d = lambda c: Document(page_content=c, metadata={"chunk_id": c})
fused = reciprocal_rank_fusion([[d("a"), d("b")], [d("b"), d("c")]])
# "b" (high in both) ranks first; each doc gains metadata["rrf_score"]
```

## Test
```bash
uv run pytest packages/common/tests/test_hybrid.py packages/common/tests/test_retrieval.py -q
# pure pass; DB parts skip without TEST_DATABASE_URL
export TEST_DATABASE_URL="postgresql://…ephemeral-branch…/db"   # throwaway only
cd packages/common && uv run alembic upgrade head
uv run pytest packages/common/tests/test_hybrid.py -q            # DB fusion + abstain run
uv run ruff check packages/common && uv run ruff format --check packages/common
```

## Common mistakes
- **Adding raw lexical + cosine scores** → wrong; they're incomparable. Use RRF (rank-based).
- **Filtering in Python after `limit`** → shrinks results below `limit`; filter in SQL (we do).
- **Expecting results with an impossible `min_score`** → that's the abstention path (by design).
- **`EnsembleRetriever` import error** → not shipped in LangChain 1.x; we implement RRF ourselves.
