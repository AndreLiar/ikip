# IKIP — architecture synthesis & the measure-first thesis

> A capstone view tying the [ADRs](../adr/) and [missions](./missions/) into one narrative. The
> thesis is **not the feature list — it is the discipline**: every capability had to *earn its place
> by measurement*, and most candidates didn't. This doc is the map of what was accepted, rejected,
> and deferred — and the evidence that decided each.

## 1. The thesis in one paragraph
IKIP is a production-grade, multi-tenant **industrial RAG & document-intelligence** platform (Neon
pgvector + R2 + Azure OpenAI, ports & adapters, built story-by-story via BMAD). Its defensible claim
is **engineering judgment under measurement**: a hard grounding invariant (*every claim resolves to a
retrieved citation, or the system abstains*), tenant isolation by construction, and a habit of
**A/B-ing every "improvement" against a baseline and keeping only what wins**. The result is a system
whose *rejections* are as considered as its features — the opposite of cargo-cult RAG.

## 2. The measure-first spine (what the data decided)
Each candidate was gated on a real metric (Recall@K deterministic; Ragas faithfulness /
answer_correctness LLM-judged), not intuition.

| Candidate | Verdict | The measurement that decided it |
|---|---|---|
| BM25 / OpenSearch (dedicated search) | **Rejected** | Lexical arm ≈0 recall on NL questions (vector carries), already 0.83–0.92 on keyword queries — BM25 re-ranks an already-good set ([MISSION-046](./missions/MISSION-046/mission.md)) |
| French analyzer | **Rejected** | No NL gain, *worse* on identifier matching (stemming mangles legal refs) — M-046 |
| Stage-1 auto-merge (ADR 0029) | **Neutral** → opt-in | Recall-vs-dedup wash at n=18; the n=5 "regression" was noise ([MISSION-044](./missions/MISSION-044/mission.md)) |
| Query rewrite (single-query) | **Rejected** | Flat on NTRS; *hurt* multi-hop (reformulating one query can't separate hops) |
| Context: dedup | **Rejected** | −0.096 context_precision, hurt answer_correctness ([MISSION-047](./missions/MISSION-047/mission.md)) |
| Context: lost-in-the-middle reorder | **Promote-candidate** | Judge-averaged faithfulness **+0.076** (~18× noise floor), recall-neutral — M-047 |
| Cross-encoder reranker | **Deferred (design-only)** | Measured headroom small (recall 0.89, faithfulness ~0.9–1.0) vs certain torch cost → built the port seam, committed **zero deps** ([MISSION-048](./missions/MISSION-048/mission.md)) |
| Agentic query decomposition | **Accepted** | Multi-hop recall collapses 0.89→0.44→0.28; cheap fixes ruled out; only decomposition recovers (→0.89); Ragas **answer_correctness +0.259** ([MISSION-049](./missions/MISSION-049/mission.md)/[050](./missions/MISSION-050/mission.md)) |

The pattern is the point: **5 rejected/deferred, 2 promoted.** The gate cut both ways.

## 3. Architecture at a glance
Two planes (ADR 0002), one grounding contract, everything swappable behind ports (ADR 0021).

```mermaid
flowchart LR
  subgraph Build["Build-time plane — Dagster (ADR 0002/0025)"]
    I[Ingest: R2 PDFs] --> X[Extract: PyMuPDF/OCR/Docling router ADR 0024]
    X --> C[Chunk: structure-aware + parent/child ADR 0019/0029]
    C --> E[Embed: text-embedding-3-small@512 ADR 0020]
    E --> KB[(Neon pgvector · halfvec ADR 0015/0027)]
  end
  subgraph Req["Request-time plane — LangGraph + ports (ADR 0022)"]
    Q[/ask] --> R{router}
    R -->|simple| H[hybrid retrieve: lexical+vector, RRF ADR 0004]
    R -->|multi-part| D[decompose → fan-out → merge ADR 0033]
    D --> H
    H --> RK[Reranker port: identity→x-enc]
    RK --> G[generate: gpt-5.4-mini ADR 0022]
    G --> V[grounding validator]
    V -->|claim⇒citation| A[cited answer]
    V -->|insufficient| AB[abstain]
  end
  KB -. tenant-scoped, version-aware .-> H
  MEM[(memory: conversation + long-term ADR 0032)] -. shapes WHAT we retrieve, never WHAT we claim .-> R
```

**Ports** (local-first, cloud-ready — ADR 0003): `LLMClient`/`EmbeddingClient` (Azure), `Cache`
(Redis/Postgres), `Reranker` (identity→cross-encoder), `Tool` (agentic), `TextExtractor`/`OcrEngine`,
`VisionCaptioner`, `PiiScrubber`, `SecretsProvider`. Each has a fake → the request-time stack is
testable with **no network/DB** (the fast `validate` CI lane).

## 4. The invariants that never bent
- **Grounding (ADR 0022):** a claim without a retrieved citation is dropped or the system abstains —
  held through memory (ADR 0032), structured facts (ADR 0030), multimodal captions (ADR 0031) and
  the agentic layer (ADR 0033), each of which changes *what we retrieve*, never *what we claim*.
- **Tenant isolation (NFR10):** structural, not a check — retrieval is tenant-scoped SQL; agentic
  tools bind their tenant at construction (`invoke` can't be redirected).
- **Framework boundary (ADR 0021):** LangChain/LangGraph reused *behind* our ports; schema,
  citations, isolation, versioning, and the agentic controller's guardrails stay in code we own.
- **Measurement as a gate (ADR 0016):** a custom deterministic harness + Ragas, compared; nothing
  becomes default without beating baseline.

## 5. ADR map (33 decisions, by theme)
- **Infra/platform:** 0001 pgvector · 0005 Container Apps · 0006 monorepo · 0010 Foundry · 0012
  local-first · 0013 OTel+Langfuse · 0014 R2 · 0015 Neon · 0023 BFF.
- **Data layer:** 0017 SQLAlchemy+Alembic · 0018 Pydantic+Pandera · 0019 chunking · 0020 embeddings
  · 0027 halfvec→Qdrant · 0029 parent/child.
- **Retrieval & answer:** 0004 hybrid-on-Postgres · 0007 LLMClient · 0021 framework boundary · 0022
  grounded answer · 0009 caching · 0026 agentic direction · 0033 agentic foundation+decomposition.
- **Ingestion/extraction:** 0024 extraction routing · 0025 ingestion triggering.
- **Eval & scope:** 0016 eval harness · 0028 build-vs-buy · 0002 dual orchestration · 0003 ports.
- **Post-MVP epics:** 0030 financial/structured · 0031 multimodal · 0032 memory & context.

## 6. Deferred — and the trigger that would un-defer it
Honest roadmap; nothing built on spec.

| Deferred | Trigger to build |
|---|---|
| Qdrant (ADR 0027) | pgvector recall/latency ceiling at scale |
| Cross-encoder reranker (ADR 0032 §3) | a measured ranking gap the bi-encoder can't close |
| litm reorder → default | a `--runs`-averaged generation-variance re-test holds the +0.076 |
| Agentic cyclic controller / checkpointer (ADR 0033) | a capability needing durable/resumable multi-step state |
| Multi-corpus routing (Epic 10.4) | a multi-domain single-tenant corpus (cross-corpus demand) |
| Native multimodal (ADR 0031) | caption-and-embed recall ceiling on diagrams |
| OpenSearch | the lexical arm becomes the measured bottleneck (M-046 says it isn't) |

## 7. How to defend it (the narrative)
*"I didn't add features because they're fashionable — I built a measurement harness first, then let it
decide. BM25, dedup, query-rewrite, the French analyzer: measured, rejected. The cross-encoder:
measured as not-yet-worth-its-dependency, so I built the seam and stopped. litm and decomposition:
measured as real wins, so I shipped them — decomposition only after proving the cheap fixes (bigger k,
rewrite) couldn't touch the multi-hop failure. The grounding invariant and tenant isolation held
through every one. The discipline is the contribution."*

## See also
[concepts/](./concepts/) (the how) · [missions/](./missions/) (the evidence) · [adr/](../adr/) (the
decisions) · [index](./index.md).
