# MISSION-014 — Reproduction tutorial

Build the two retrieval arms + the LangChain adapter. Concept: [retrieval](../../concepts/retrieval.md);
decisions [ADR 0004](../../../adr/0004-hybrid-retrieval-on-postgres.md), [ADR 0021](../../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md).

## Prerequisites
- Story 3.2 done (embeddings). `uv sync --group embeddings`. A Postgres+pgvector for DB tests.

## Migrate
```bash
cd packages/common
uv run alembic upgrade head        # applies 3a15a5ad99fe: content_tsv + GIN + HNSW
# sanity (no DB): offline render
uv run alembic upgrade 1aa8f27570e7:3a15a5ad99fe --sql
uv run alembic downgrade 3a15a5ad99fe:1aa8f27570e7 --sql
```

## Use the search (Python)
```python
from ikip_common.db.retrieval import lexical_search, vector_search
from ikip_common.llm import build_embedding_client

hits = lexical_search(session, tenant_id, "E42")                 # keyword/exact
client = build_embedding_client()
[qvec] = client.embed(["pump overheating fault"])
hits = vector_search(session, tenant_id, qvec, model_version=client.model_version)  # semantic
# every hit carries document_id/version/revision/section/page -> citations (FR16)
```

## Use via LangChain (the adapter)
```python
from ikip_common.llm.retriever import IkipRetriever
from ikip_common.llm import build_embedding_client

retriever = IkipRetriever(session=session, tenant_id=tenant_id, arm="lexical")
docs = retriever.invoke("E42")                      # list[langchain_core.documents.Document]

vretriever = IkipRetriever(
    session=session, tenant_id=tenant_id, arm="vector",
    embedding_client=build_embedding_client(),
)
docs = vretriever.invoke("pump overheating")        # citations in doc.metadata
```

## Test
```bash
uv run pytest packages/common/tests/test_retrieval.py packages/common/tests/test_retriever_adapter.py -q
# pure parts pass; DB parts skip without TEST_DATABASE_URL
export TEST_DATABASE_URL="postgresql://…ephemeral-branch…/db"   # throwaway only!
uv run pytest packages/common/tests/test_retrieval.py -q         # DB parts run
uv run ruff check packages/common && uv run ruff format --check packages/common
```

## Common mistakes
- **`type "vector" does not exist`** → run `alembic upgrade head` (the embedding migration creates the extension).
- **Lexical returns nothing for a stemmed word** → config is `simple` (no stemming); search the exact token, or rely on the vector arm for meaning.
- **Vector search empty** → the `model_version` filter must match the stored embeddings' version.
- **`IkipRetriever` import error in CI** → `langchain_core` is only in the `embeddings` group; tests `importorskip` it.
