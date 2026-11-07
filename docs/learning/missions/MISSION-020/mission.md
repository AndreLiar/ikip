# MISSION-020 — Build-time embedding pipeline: close the Epic 2 ↔ Epic 3 loop

**Mode:** Autonome (compose already-built, tested pieces) + knowledge transfer.
**Objective:** add the missing build-time stage — turn a document version's curated text into `Section` + `Chunk` + `Embedding` rows (pgvector), so retrieval (`/retrieve`, `/ask`) actually has data. Wire it as a Dagster asset downstream of versioning.
**Maps to:** Epic 2 ↔ Epic 3 integration. Uses Story 3.1 (`chunk_document`), 3.2 (`embed_and_store`), 3.3 (indexes). Applies [ADR 0002](../../../adr/0002-dual-orchestration-dagster-langgraph.md) (Dagster = build-time).

## The gap it fills
`chunk_document` and `embed_and_store` existed + were unit-tested, but **nothing in the pipeline called them** — the Dagster graph stopped at `document_versions` (placeholder), so `chunk`/`embedding` stayed empty and retrieval would always abstain. This mission is the `chunk → embed → index` stage.

## What was built
- **`ikip_docproc/indexing.py` `index_version(session, tenant_id, document_version_id, curated_text, embedding_client)`** — pure, port-injected (SQLAlchemy `Session` + `EmbeddingClient`), langchain-free:
  1. `chunk_document(curated_text)` → specs,
  2. `plan_sections` groups specs by `section_path` → persists `Section` rows (heading, hierarchy_path, ordinal, page range),
  3. persists tenant-scoped `Chunk` rows (content, page range, token_count, metadata),
  4. `embed_and_store` → vectors in pgvector.
  - **Idempotent / rerun-safe:** if the version was already chunked, it does NOT duplicate sections/chunks — it just re-embeds existing chunks (`embed_and_store` is idempotent per `(chunk_id, model_version)`, FR14).
- **Dagster asset `embedded_chunks`** (downstream of `document_versions`): for each **current** version with a `curated_object_key`, fetch curated text from R2 and `index_version` with the Azure embedding client. Idempotent → asset-rerun-safe (Story 2.6 theme).
- `ikip-ingestion` now depends on `ikip-docproc` (build-time indexing).

## Acceptance (self-set)
1. `index_version` persists Section/Chunk/Embedding and is langchain-free. — **[verified]** (import check; DB test)
2. Closed loop: after indexing, `lexical_search` + `vector_search` find the chunk with citations (doc/version). — **[verified]** (`test_index_version_populates_and_is_retrievable`, DB-gated)
3. Re-indexing a version does not duplicate sections/chunks. — **[verified]** (`test_index_version_is_idempotent`, DB-gated)
4. Section planning groups by path/order. — **[verified]** (pure `test_plan_sections...`)
5. Dagster `embedded_chunks` wired downstream; `defs` load. — **[verified]** (import under `--group dagster`)
6. No regression. — **[verified]** (143 passed, 34 skipped; ruff/format OK)

## Honest remaining gaps (not in scope here)
- `curated_documents` / `document_versions` are still **placeholders**: real extraction/clean/curated-storage + actual version persistence (via `publish_document_version`) is Epic 2 completion. Until a version has a `curated_object_key`, `embedded_chunks` processes 0 — the stage is correct and tested, it just has no upstream data yet in the skeleton.

## Deliverables
- `services/document-processing/src/ikip_docproc/indexing.py` + export; `tests/test_indexing.py` (1 pure + 2 DB-gated).
- `services/ingestion/.../definitions.py` `embedded_chunks` asset; `ikip-ingestion` → `ikip-docproc` dep.

## Concepts
Reuses [chunking](../../concepts/chunking.md), [embeddings](../../concepts/embeddings.md), [retrieval](../../concepts/retrieval.md), [rag-orchestration](../../concepts/rag-orchestration.md), [dagster-orchestration](../../concepts/dagster-orchestration.md).
