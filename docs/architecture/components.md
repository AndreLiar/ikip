# Components

_Sharded from `../architecture.md`. Part of the [architecture index](./index.md)._

| Component                        | Responsibility                                                             | Depends on                                            |
| -------------------------------- | -------------------------------------------------------------------------- | ----------------------------------------------------- |
| `apps/api` (FastAPI)           | REST surface, auth, authorization, tenant scoping, orchestrates RAG + jobs | repositories, interfaces, RAG service                 |
| `apps/web` (Next.js)           | Search, chat, document viewer, admin, dashboards                           | `apps/api`                                          |
| `services/ingestion`           | Connectors, scheduled sync, raw capture                                    | `ObjectStorage`, `JobQueue`, Dagster              |
| `services/document-processing` | Parse, OCR fallback, clean, validate, dedup, version, enrich               | `ObjectStorage`, Dagster, PyMuPDF/Docling/Tesseract |
| `services/indexing`            | Chunking, embeddings, full-text + vector index                             | `VectorStore`, `LLMClient`, PostgreSQL            |
| `services/retrieval`           | BM25 + vector + hybrid + rerank + filters + LangGraph RAG                  | `VectorStore`, `LLMClient`, repositories          |
| `services/evaluation`          | Gold datasets, Recall@K, citation/groundedness/safety eval                 | retrieval, datasets                                   |
| `packages/common`              | Shared models, interfaces, tenant utilities                                | —                                                    |
| `packages/ai-clients`          | Pluggable LLM/embedding adapters                                           | Azure OpenAI                                          |

> Infrastructure dependencies named as interfaces (`ObjectStorage`, `JobQueue`, `VectorStore`, `LLMClient`, `SecretsProvider`, `Telemetry`, `Cache`, `PiiScrubber`) live in `packages/common` and are implemented by local + Azure/prod adapters — see [ADR 0003](../adr/0003-local-first-ports-and-adapters.md).
