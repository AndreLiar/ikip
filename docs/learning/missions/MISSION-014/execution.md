# MISSION-014 — Execution log

Evidence labels: `[verified]` run with output · `[untested]`. Secrets redacted.

## Step 1 — Model + migration — [verified]
- `db/models.py`: `Chunk.content_tsv` = `TSVECTOR` `Computed("to_tsvector('simple', content)", persisted=True)` + GIN index `ix_chunk_content_tsv`; `Embedding` HNSW index `ix_embedding_vector_hnsw` (`vector_cosine_ops`). `FTS_CONFIG = "simple"` constant.
- Migration `3a15a5ad99fe` (down_revision `1aa8f27570e7`), hand-written. Offline SQL render verified **both ways**:
```
upgrade:   ALTER TABLE chunk ADD COLUMN content_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;
           CREATE INDEX ix_chunk_content_tsv ON chunk USING gin (content_tsv);
           CREATE INDEX ix_embedding_vector_hnsw ON embedding USING hnsw (vector vector_cosine_ops);
downgrade: DROP INDEX ... ; ALTER TABLE chunk DROP COLUMN content_tsv;
```

## Step 2 — Retrieval SQL — [verified]
`db/retrieval.py`: `lexical_search` (`websearch_to_tsquery('simple', q)` + `content_tsv @@ q`, ranked by `ts_rank`), `vector_search` (`Embedding.vector.cosine_distance(qvec)`, filtered by `model_version`), `SearchHit` with the full citation chain, `_timed` logs `arm/tenant/latency_ms` (AC4). Statement builders `_lexical_stmt`/`_vector_stmt` extracted so the SQL shape is pure-testable.

## Step 3 — LangChain boundary — [verified]
`llm/retriever.py`: `IkipRetriever(BaseRetriever)` delegates to our SQL (vector arm embeds the query via the `EmbeddingClient` port) and `hit_to_document` maps each hit to a `Document` with the citation in `metadata`. Imports `langchain_core` at module top → not auto-imported from `ikip_common.llm`; tests `importorskip`.

## Step 4 — Tests + gate — [verified]
```
uv run pytest packages/common/tests/test_retrieval.py packages/common/tests/test_retriever_adapter.py -q
# 6 passed, 4 skipped (DB)
uv run pytest packages/common/tests -q        # 27 passed, 25 skipped
uv run ruff check packages/common             # OK
uv run ruff format --check packages/common    # OK (41 files)
```
- Pure: SQL shape (simple FTS via `FTS_CONFIG`, `websearch_to_tsquery`, `@@`, `ts_rank`, `<=>`, `model_version`, `tenant_id`, citation joins); `hit_to_document` metadata; arm validation (`BaseRetriever` is pydantic → constructed with a bare `Session()`).
- DB-gated (CI ephemeral Neon branch): lexical finds by term with citation; vector returns with citation + `model_version` filter; **tenant isolation** both arms (NFR10); `IkipRetriever` lexical+vector return Documents with citation metadata.

**Pitfalls hit:**
- `literal_binds` compile failed on the `'simple'` **REGCONFIG** value (no literal renderer) → assert `FTS_CONFIG == "simple"` directly + compile without literal binds.
- `IkipRetriever(session=object())` fails pydantic `arbitrary_types_allowed` isinstance → use a real bare `Session()`.

**Local DB caveat:** no Docker/Neon branch locally → DB tests run in CI; migration verified via offline render.
