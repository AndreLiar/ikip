# MISSION-023 — Ingestion robustness: HTML de-boilerplate, content_type persistence, tunable embedding batch

**Mode:** Autonome (three related follow-ups from the live pipeline run) + knowledge transfer.
**Objective:** improve curated-text quality and ingestion robustness surfaced by the real run (MISSION-021/022 + the live K8s ingest).
**Maps to:** Epic 2 polish (Stories 2.2/2.3/2.4) + Story 3.2 hardening.

## What was built
### 1. HTML de-boilerplate (main-content extraction)
`curation._strip_html` now drops boilerplate regions (`script/style/nav/header/footer/aside/form`, tag + contents) and, when the page marks a main region, keeps the **largest `<main>`/`<article>`** block before stripping remaining tags. Pure heuristic, no dependency; `trafilatura`-grade extraction remains a future adapter. Removes the menu/cookie/version-picker noise that was polluting curated text + lexical retrieval.

### 2. Persist `content_type` on the ingestion job
- Model: `IngestionJob.content_type` (nullable String) + reversible migration `21448dfe68a6`.
- `IngestionJobRepository.create(..., content_type=None)`; `ingest_documents` captures `doc.content_type`; the `document_versions` asset passes `job.content_type` to `curate_and_version`. Curation uses it directly; the content-sniff stays a fallback for NULL (older jobs).

### 3. Tunable embedding batch size
`Settings.embedding_batch_size` (`EMBEDDING_BATCH_SIZE`, default 16) wired into `AzureOpenAIEmbeddingClient`; batching + 429 backoff (MISSION-fix) cap per-minute load on the low S0 tier. Runbook `dev-on-azure-cost-control.md` documents the three mitigations (smaller batch → bump Terraform capacity → portal quota increase).

## Acceptance (self-set)
1. HTML boilerplate removed, main content kept. — **[verified]** (`test_curation.py::test_curate_drops_boilerplate_and_keeps_main`)
2. `content_type` captured on the job + threaded to curation. — **[verified]** (`test_ingest.py` asserts job.content_type; migration offline-rendered both ways)
3. Batch size configurable from Settings. — **[verified]** (`test_embeddings_batch.py`; `EMBEDDING_BATCH_SIZE` in config + .env.example)
4. No regression. — **[verified]** (158 passed, 32 skipped; ruff/format OK; Dagster defs load)

## Deliverables
- `ikip_docproc/curation.py` (`_strip_html`, boilerplate/main-region regexes).
- `ikip_common/db/models.py` + migration `21448dfe68a6`; `db/ingestion.py` create(content_type).
- `ikip_ingestion/ingest.py` + `definitions.py` (thread content_type).
- `ikip_common/config.py` `embedding_batch_size`; `llm/azure.py` wiring; `.env.example`.
- `docs/runbooks/dev-on-azure-cost-control.md` (quota section). Tests updated.

## Concepts
Reuses [pdf-extraction](../../concepts/pdf-extraction.md), [data-validation](../../concepts/data-validation.md), [embeddings](../../concepts/embeddings.md), [config-12-factor](../../concepts/config-12-factor.md).
