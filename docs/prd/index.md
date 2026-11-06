# IKIP PRD — Sharded Epics (Index)

_Sharded from `../prd.md` (BMAD PO step). Each file holds one epic's goal and its stories with acceptance criteria. Global requirements (FR1–FR33, NFR1–NFR18), UI goals and technical assumptions remain in the parent `../prd.md`._

| Epic | Title | File |
|------|-------|------|
| 1 | Foundation & Platform Core | [`epic-1-foundation-platform-core.md`](./epic-1-foundation-platform-core.md) |
| 2 | Data Engineering & Ingestion Pipeline | [`epic-2-data-engineering-ingestion.md`](./epic-2-data-engineering-ingestion.md) |
| 3 | Retrieval & RAG Engineering | [`epic-3-retrieval-rag.md`](./epic-3-retrieval-rag.md) |
| 4 | Enterprise Application & SaaS | [`epic-4-enterprise-application-saas.md`](./epic-4-enterprise-application-saas.md) |
| 5 | LLMOps, Evaluation & Observability | [`epic-5-llmops-evaluation-observability.md`](./epic-5-llmops-evaluation-observability.md) |
| 6 | Security, Governance & Cloud Operations | [`epic-6-security-governance-cloud-ops.md`](./epic-6-security-governance-cloud-ops.md) |

### Post-MVP expansion epics (sequenced after Epics 1–6)

| Epic | Title | File |
|------|-------|------|
| 7 | Enterprise Knowledge Connectors | [`epic-7-enterprise-knowledge-connectors.md`](./epic-7-enterprise-knowledge-connectors.md) |
| 8 | Structured-Data & Financial Retrieval | [`epic-8-structured-data-financial-retrieval.md`](./epic-8-structured-data-financial-retrieval.md) |
| 9 | Advanced Multimodal Retrieval | [`epic-9-advanced-multimodal-retrieval.md`](./epic-9-advanced-multimodal-retrieval.md) |

## Reference
- Parent PRD: [`../prd.md`](../prd.md) — requirements, UI goals, technical assumptions, next steps
- Project Brief: [`../brief.md`](../brief.md)
- Architecture: [`../architecture.md`](../architecture.md)
- Data Sources appendix: [`../data-sources.md`](../data-sources.md)

## Build order
Epics are sequential and each delivers a deployable increment. Implement story-by-story (SM → Dev), validating against acceptance criteria and the architecture's coding/test/security standards. Start with Epic 1.
