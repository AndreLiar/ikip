# IKIP — Learning log (execution-as-teaching)

Mission notes record how each non-trivial implementation was built **and** how to reproduce it without an agent. Architecture decisions live in [`../adr/`](../adr/README.md); reproduction/runbooks in [`../runbooks/`](../runbooks); these notes cross-link them.

## Missions
| Mission | Scope | Story |
|---------|-------|-------|
| [MISSION-001](./missions/MISSION-001/mission.md) | Monorepo scaffold, tooling & conventions | Epic 1 / Story 1.1 |
| [MISSION-002](./missions/MISSION-002/mission.md) | Configuration layer & connectivity doctor | Epic 1 / Story 1.2 |
| [MISSION-003](./missions/MISSION-003/mission.md) | FastAPI skeleton & health endpoint | Epic 1 / Story 1.3 |
| [MISSION-004](./missions/MISSION-004/mission.md) | Multi-tenant data foundation (models, migrations, repo) | Epic 1 / Story 1.5 |
| [MISSION-005](./missions/MISSION-005/mission.md) | Authentication & RBAC (JWT, Principal, role hierarchy) | Epic 1 / Story 1.6 |
| [MISSION-006](./missions/MISSION-006/mission.md) | Object storage port (R2) & ingestion-job model | Epic 2 / Story 2.1 |
| [MISSION-007](./missions/MISSION-007/mission.md) | Source connectors & Dagster orchestration | Epic 2 / Story 2.2 |
| [MISSION-008](./missions/MISSION-008/mission.md) | PDF extraction with OCR fallback (two-stage) | Epic 2 / Story 2.3 |
| [MISSION-009](./missions/MISSION-009/mission.md) | Cleaning, normalization, metadata & validation | Epic 2 / Story 2.4 |
| [MISSION-010](./missions/MISSION-010/mission.md) | Deduplication & document versioning | Epic 2 / Story 2.5 |
| [MISSION-011](./missions/MISSION-011/mission.md) | Lineage, quality reporting & reprocessing | Epic 2 / Story 2.6 |
| [MISSION-012](./missions/MISSION-012/mission.md) | Structure-aware chunking | Epic 3 / Story 3.1 |
| [MISSION-013](./missions/MISSION-013/mission.md) | Embeddings generation & version management (+ Azure OpenAI via Terraform) | Epic 3 / Story 3.2 |
| [MISSION-014](./missions/MISSION-014/mission.md) | Lexical & vector search (tsvector/GIN + pgvector/HNSW; LangChain BaseRetriever) | Epic 3 / Story 3.3 |
| [MISSION-015](./missions/MISSION-015/mission.md) | Hybrid retrieval, reranking & filters (RRF, Reranker port, version-aware filters, abstention) | Epic 3 / Story 3.4 |
| [MISSION-016](./missions/MISSION-016/mission.md) | LangGraph grounded-answer service (gpt-5.4-mini, server-resolved citations, grounding validation) | Epic 3 / Story 3.5 |
| [MISSION-017](./missions/MISSION-017/mission.md) | Retrieval & answer quality baseline (deterministic metrics, gold set, regression reports) | Epic 3 / Story 3.6 |
| [MISSION-018](./missions/MISSION-018/mission.md) | Caching (Cache port, tenant/version-aware keys, invalidation, exact-match answer cache) | Epic 3 / Story 3.7 |
| [MISSION-019](./missions/MISSION-019/mission.md) | Wire Epic 3 hooks: cache invalidation at ingestion + hybrid-retrieval/ask endpoints | Epic 3 / integration |
| [MISSION-020](./missions/MISSION-020/mission.md) | Build-time embedding pipeline (index_version + Dagster embedded_chunks asset) — closes Epic 2↔3 | Epic 2↔3 / build-time |
| [MISSION-021](./missions/MISSION-021/mission.md) | Complete Epic 2: curation → version persistence (curate_and_version + real document_versions asset) | Epic 2 / build-time |
| [MISSION-022](./missions/MISSION-022/mission.md) | Real PDF extraction adapter (PdfExtractor: PyMuPDF→OCR) behind the TextExtractor seam | Epic 2 / Story 2.3 |
| [MISSION-023](./missions/MISSION-023/mission.md) | Ingestion robustness: HTML de-boilerplate, content_type persistence, tunable embedding batch | Epic 2/3 / polish |
| [MISSION-024](./missions/MISSION-024/mission.md) | Technician Assistant UI (Next.js BFF) + keyword/semantic/hybrid search modes | Epic 4 / Story 4.4 |
| [MISSION-025](./missions/MISSION-025/mission.md) | Conversation history & feedback (Story 4.6) — Epic 4 8/8 | Epic 4 / Story 4.6 |

## Concepts (write-once, reused across missions)
| Concept | Covers |
|---------|--------|
| [dev-tooling](./concepts/dev-tooling.md) | lint vs format, ruff, pytest, pnpm workspaces, prettier, eslint flat, tsconfig |
| [config-12-factor](./concepts/config-12-factor.md) | env-based config, Pydantic Settings, SecretStr, fail-fast, hermetic tests |
| [health-checks](./concepts/health-checks.md) | liveness vs readiness, dependency probes, 503-on-degraded, mockability |
| [multi-tenancy](./concepts/multi-tenancy.md) | isolation models, `tenant_id` + repository scoping, RLS backstop, proving isolation |
| [auth-rbac](./concepts/auth-rbac.md) | authn vs authz, JWT, Principal, role hierarchy, dev-token vs Entra ID |
| [object-storage](./concepts/object-storage.md) | blobs vs DB, S3 abstraction, ObjectStorage port, artifact tiers, presigned URLs |
| [dagster-orchestration](./concepts/dagster-orchestration.md) | assets, schedules, Definitions, thin-wrapper pattern, keeping CI fast |
| [pdf-extraction](./concepts/pdf-extraction.md) | native vs scanned, two-stage PyMuPDF→OCR, quality scoring, optional engines |
| [data-validation](./concepts/data-validation.md) | cleaning, Pydantic-vs-Pandera, report-not-raise, regex negative cases |
| [dedup-versioning](./concepts/dedup-versioning.md) | exact vs near-dup, SimHash, supersede-not-delete, migration enum trap |
| [lineage-reprocessing](./concepts/lineage-reprocessing.md) | asset lineage, quality report, retry/dead-letter, asset-aware reprocessing |
| [why-rag](./concepts/why-rag.md) | why the context window isn't enough; cost/latency/quality/security/citations → RAG |
| [chunking](./concepts/chunking.md) | chunking strategies, structure-aware + overlap, tokens, citation chain · 🇫🇷 [strategies](./concepts/chunking-strategies.fr.md) |
| [embeddings](./concepts/embeddings.md) | vectors, dimensions, Matryoshka reduction, model_version (additive re-embed), cost, port+fake |
| [rag-orchestration](./concepts/rag-orchestration.md) | Dagster (build-time) vs LangGraph (request-time); how LangChain is used behind our ports |
| [langchain-inventory](./concepts/langchain-inventory.md) | the 5 LangChain bricks used (+ where/port), what we built ourselves, what we deliberately avoid |
| [retrieval](./concepts/retrieval.md) | lexical (tsvector/GIN, simple) vs vector (pgvector/HNSW, cosine); citations; IkipRetriever BaseRetriever |
| [hybrid-retrieval](./concepts/hybrid-retrieval.md) | RRF fusion, Reranker port (identity→cross-encoder), version-aware filters, abstention |
| [grounded-answers](./concepts/grounded-answers.md) | LangGraph flow, opaque handles + server-resolved citations, grounding validation, reasoning vs temperature |
| [rag-evaluation](./concepts/rag-evaluation.md) | deterministic metrics (Recall@K, citation resolution/coverage), resolution≠entailment, 3-artifact regression reports |
| [caching](./concepts/caching.md) | Cache port, key-as-correctness (tenant/version/epoch), answer cache, abstention-preserving hits, semantic deferred |
