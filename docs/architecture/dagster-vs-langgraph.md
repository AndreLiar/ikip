# Why both Dagster *and* LangGraph? (two orchestrators, two jobs)

_Explainer companion to [ADR 0002](../adr/0002-dual-orchestration-dagster-langgraph.md). Part of the [architecture index](./index.md). Answers: "Both are 'orchestrators' — why do we need two?"_

---

## One-sentence answer

> **Dagster orchestrates the *data* — building and maintaining the knowledge base.
> LangGraph orchestrates the *AI reasoning* — answering one technician's question.**

They are both "orchestrators," which is exactly why they get confused — but they orchestrate **different things, on different clocks, with different failure models.** IKIP has two pipelines, and each wants the tool built for its job.

| | **Dagster** | **LangGraph** |
|---|---|---|
| Orchestrates | data assets (documents → chunks → embeddings → index) | AI workflow steps (analyze → retrieve → rerank → cite/abstain) |
| When it runs | **batch** — scheduled / event-driven | **request-time** — when a user asks |
| Builds or reads the KB | **writes** the knowledge base | **reads** the knowledge base |
| Timescale | minutes–hours (backfills: longer) | sub-seconds–seconds (p95 TTFT < 5 s) |
| Unit of work | a data asset (with lineage) | a node in a stateful graph |
| "Done" means | the corpus is ingested, validated, indexed | this answer is grounded + cited, or it abstained |

---

## The two pipelines (they share data, never a runtime)

```
Pipeline A — DATA ENGINEERING  (Dagster, batch)              Pipeline B — RAG  (LangGraph, request-time)
───────────────────────────────────────────────            ──────────────────────────────────────────
sources → parse/OCR → clean → dedup → version →             question → authorize → analyze → retrieve →
enrich → chunk → embed → index                              rerank → sufficiency? → cite / abstain
        │                                                             ▲
        └──────────▶  PostgreSQL + pgvector  ◀────────────────────────┘
                      Object storage (raw/cleaned/curated)
```

**Dagster builds the library and keeps it current. LangGraph is the librarian who, when asked, fetches the right evidence and decides how to answer.** The only thing they share is the data model (PostgreSQL + object storage) — Pipeline A writes it, Pipeline B reads it. They have **no shared execution runtime.**

---

## Why not use one tool for both?

### Could LangGraph replace Dagster? (do ingestion as graph nodes)
Technically yes — LangGraph has durable execution, so you *could* model ingestion as nodes. But then you'd hand-build everything a data platform gives you for free, and a serious industrial corpus demands answers to questions LangGraph has no native concept of:

- *Which documents failed ingestion yesterday?*
- *Which source hasn't synchronized in 7 days?*
- *Reprocess every document after we change the PDF parser — without rebuilding everything.*
- *Backfill 200,000 documents.*
- *Which data assets depend on this changed source?*
- *Did a data-quality check fail for this batch?*

Dagster answers these with **schedules, sensors, asset lineage, backfills, partitions and asset-aware reprocessing** as first-class features (FR7, FR8, NFR15; Story 2.6). Rebuilding them around LangGraph is reinventing a data-orchestration platform.

### Could Dagster replace LangGraph? (do RAG as a Dagster job)
No. Dagster is built for **batch data assets**, not **stateful, conditional, request-time reasoning** with a sub-second latency budget, an abstention branch, human-in-the-loop and per-query tracing (FR14–FR18, FR30; Stories 3.5, 5.4). Running a technician's live question through a batch asset graph is the wrong execution model — see [why-langgraph.md](./why-langgraph.md) for what that request-time workflow actually needs.

**So they are complementary, not interchangeable.** Each is wrong for the other's job.

> **The honest framing (same as for LangGraph):** none of this *requires* Dagster — schedules (cron), lineage (your own metadata), backfills (scripts) and data-quality checks can all be hand-built in pure Python. The question is **build vs. buy**: Dagster is a *data platform* you adopt so you don't re-implement and maintain scheduling, lineage, backfills, partitions and asset-aware reprocessing yourself. Plus the project's stated learning goal is to master Dagster as an industry-standard tool. See the same reasoning for the AI side in [why-langgraph.md → "Couldn't I just build this in pure Python?"](./why-langgraph.md#couldnt-i-just-build-this-in-pure-python-no-langchain-no-langgraph).

---

## The boundary (what each owns)

| Concern | Owner |
|---|---|
| Downloading, parsing, OCR, cleaning, validating sources | **Dagster** |
| Deduplication, document versioning, lineage | **Dagster** |
| Chunking, embedding, building the search index | **Dagster** |
| Scheduled sync, "is a manual updated?", reprocessing, backfills | **Dagster** |
| Authorizing a query, analyzing intent, identifying equipment | **LangGraph** |
| Hybrid retrieval + rerank at request time | **LangGraph** |
| Sufficiency check → cited generation **or** abstention | **LangGraph** |
| Per-query tracing (latency, cost, path taken) | **LangGraph** |

> Design note: Dagster should **orchestrate and observe** heavy processing, not necessarily run it inside its own process — it can trigger container workers / Container Apps Jobs. Likewise LangGraph orchestrates AI decisions; it is **not** the job queue, database or file store.

---

## Concrete IKIP examples

- **Dagster, every night:** check manufacturer portals for updated manuals; ingest new revisions; supersede obsolete ones; re-embed only what changed; publish a data-quality report. (Nobody is waiting on a screen.)
- **LangGraph, right now:** a technician asks about a fault; authorize → identify model/revision → retrieve the *applicable* procedure → verify sufficiency → answer with citations, or abstain. (Someone *is* waiting — latency and safety matter.)

Example of the handoff: Dagster detects and ingests a new manual revision overnight; the next morning LangGraph retrieves **that** revision and marks the previous one obsolete — version-aware retrieval (FR14) only works because the data pipeline tracked the version (Story 2.5).

---

## Analogy

- **Dagster** = the factory + supply chain that manufactures parts and keeps the warehouse stocked, labelled and audited — scheduled, batch, with full traceability of where every item came from.
- **LangGraph** = the expert on the floor who, when a technician walks up with a problem, fetches the right part from that warehouse and decides what to do — fast, interactive, and able to say *"I don't have what you need"* rather than guess.

Or in engineering terms: **Dagster = the build/ETL system; LangGraph = the request handler / state machine.**

---

## How they map to the diagrams

| Diagram | Dagster | LangGraph |
|---|---|---|
| [System Context](./img/01_system_context.png) | left: "Data Engineering — Dagster (batch)" → writes KB | right: "RAG Orchestration — LangGraph" → reads KB |
| [Data Engineering Pipeline](./img/02_ingestion_pipeline.png) | the whole diagram | — |
| [RAG Workflow](./img/03_rag_workflow.png) | — | the whole diagram |

---

## Bottom line

Two pipelines, two clocks, two failure models → two orchestrators. **Dagster makes the data AI-ready (and keeps it that way); LangGraph makes the AI use that data reliably and safely.** Using only one would mean either reinventing a data platform inside an AI framework, or forcing live reasoning through a batch engine. Running both is what lets IKIP be *both* a real data-engineering platform *and* a trustworthy RAG system.

> Decision record: [ADR 0002 — Dual orchestration](../adr/0002-dual-orchestration-dagster-langgraph.md). Its "Revisit When" notes the collapse option: a *small* system could drop Dagster and do ingestion in LangGraph — IKIP's lineage, backfill, scheduled-sync and data-quality needs are what justify keeping both.
