# Epic 8 — Structured-Data & Financial Retrieval  (Post-MVP)

_Sharded from `../prd.md`. Part of the [epic index](./index.md). **Post-MVP** — sequenced after Epics 1–6; not part of the initial production scope._

> **Status (2026-11-16): core delivered** ([ADR 0030](../adr/0030-structured-financial-data-retrieval.md)). 8.1 typed `financial_fact` store + SEC XBRL extractor (#107); 8.2 numeric retrieval + comparison + abstention (#108), NL router + numeric-guarded answer (#109), figure+narrative fusion (#110); 8.3 deterministic numeric-accuracy eval + gate (#111). **Remaining for production**: wire a `finance-sec` tenant through the ingestion pipeline (link facts → `DocumentVersion`), adapt the real hybrid retriever into `DocEvidence`, and expand the XBRL taxonomy/dimensional coverage (deferred per ADR 0030).

**Goal:** Add the ability to retrieve and reason over structured data (financial statements/XBRL) alongside documents — hybrid structured+unstructured retrieval with numerical accuracy and comparative analysis — establishing the finance vertical.

**Addresses:** RAG dimension C (documents + structured data) in [`../rag-design-challenges.md`](../rag-design-challenges.md). Builds on Epic 3 (retrieval), data model.

**Architecture:** [ADR 0030](../adr/0030-structured-financial-data-retrieval.md) — typed `financial_fact` store (one datastore), `StructuredExtractor` port for XBRL, a numeric retrieval path distinct from vector search, figures **retrieved-not-generated** + cited to source/period, and deterministic exact-match/tolerance eval. Epic-8-MVP scope (point figures + simple comparisons, SEC EDGAR) is defined there.

---

## Story 8.1 Structured-Data Ingestion (statements / XBRL)
As an engineer, I want structured financial data ingested and modeled, so that exact figures are queryable.
**Acceptance Criteria:**
1. Ingest structured statements (e.g., XBRL) into a typed, queryable schema with provenance.
2. Linkage between a figure and its source document/version/page is preserved.
3. Period/effective-date semantics captured (ties to version-awareness).
4. Validation rejects malformed/ambiguous structured inputs.

## Story 8.2 Hybrid Structured + Unstructured Retrieval
As an analyst, I want queries that combine narrative documents and exact figures, so that answers are both contextual and numerically correct.
**Acceptance Criteria:**
1. Retrieval can join document evidence with structured values in one answer.
2. Numeric answers cite the exact structured source and period.
3. Abstention applies when the figure is unavailable/ambiguous.
4. Comparative queries (period-over-period, entity-vs-entity) supported.

## Story 8.3 Numerical-Accuracy Evaluation
As an evaluator, I want numerical-accuracy metrics, so that figure answers are measured, not assumed.
**Acceptance Criteria:**
1. Gold set of figure questions with known values.
2. Exact-match / tolerance metrics computed and regression-gated.
3. Citation correctness measured for figures (source + period).
4. Results stored alongside existing evaluation runs (Epic 5).
