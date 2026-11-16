# 0030. Structured financial data & numeric retrieval (Epic 8)

- **Status:** Proposed — architecture for Epic 8 (post-MVP finance vertical); no code until agreed.
- **Date:** 2026-11-16
- **Deciders:** Architect, PM
- **Related:** [Epic 8](../prd/epic-8-structured-data-financial-retrieval.md) · RAG dimension C ([rag-design-challenges](../rag-design-challenges.md)) · [ADR 0003](./0003-local-first-ports-and-adapters.md) (ports) · [ADR 0004](./0004-hybrid-retrieval-on-postgres.md) (retrieval) · [ADR 0022](./0022-grounded-answer-langgraph-gpt5-mini.md) (grounded answer) · [ADR 0016](./0016-rag-evaluation-custom-plus-ragas.md) (eval) · FR16 (citations) · NFR10 (tenant isolation)

## Context
Epic 8 adds the **finance vertical**: answer questions over **exact figures** from financial statements (XBRL, e.g. SEC EDGAR) *alongside* narrative documents — "what was revenue in FY2023, and why did it change?". The current platform is entirely **document-centric** (`document → version → section → chunk → embedding`); there is no typed numeric store and no structured-extraction path.

The defining risk of financial RAG is **numeric correctness**: an LLM must never *compute* or *paraphrase* a figure — it hallucinates digits, mis-scales units, or silently does wrong arithmetic. A revenue number that is confidently wrong is worse than an abstention. So the architecture must make exact figures **retrieved, not generated**, and **cited to their exact source + period**.

Two things we must *not* lose by adding this: the single-datastore model (ADR 0004) and the invariants that make answers trustworthy — the citation chain (FR16) and tenant isolation (NFR10).

## Decision
Add structured financial data as a **typed, tenant-scoped fact store in Postgres**, ingested behind a new extractor port, retrieved by a **numeric path distinct from vector search**, composed into answers where the LLM narrates but **never produces a number**, and measured with **exact-match/tolerance** metrics. Scope Epic-8-MVP deliberately; defer the long tail of XBRL.

### 1. Data model — `financial_fact` (new table, one datastore)
A typed fact with full provenance + period semantics, tenant-scoped (NFR10):
- **identity:** `concept` (XBRL tag, e.g. `Revenues`), `entity` (filer/CIK), `period_start`/`period_end` (duration) or `instant` (point-in-time), `dimensions` (JSONB — segment/axis members), `unit` (currency/shares), `scale`/`decimals`.
- **value:** `value_numeric` (exact `NUMERIC`, never float — no rounding), plus the raw string as filed.
- **provenance (FR16):** `document_version_id` FK (the filing it came from) + optional `section_id`/page, so a figure resolves to `fact → document_version → document → page` exactly like a chunk resolves today. Reuses `DocumentVersion`'s `effective_date`/`publication_date` + `is_current` supersession (ADR data model) — a restated figure is a new version, not an overwrite (NFR15).
- **uniqueness:** `(tenant_id, entity, concept, period, dimensions, document_version_id)` — a filing states each fact once.

### 2. Ingestion — `StructuredExtractor` port (mirror `TextExtractor`)
A new port (ADR 0003 style, `Protocol`): `extract_facts(raw_bytes, content_type) -> list[FactSpec]`. Adapter: an **XBRL parser** (lazy dependency group `xbrl`). Reuses the **existing `IngestionJob` pipeline** (Story 2.1): an XBRL filing is an ingestion job → extract facts → validate → persist `financial_fact` rows + keep the raw filing in R2 for citation. A filing is *also* a `Document` (its narrative/notes chunked as today) so structured + unstructured share one provenance root. **Validation rejects** malformed/ambiguous facts (missing period/unit, non-numeric) — recorded, not silently dropped (Story 8.1 AC4).

### 3. Retrieval — a numeric path, fused with document retrieval
Numeric queries are **not** a vector-similarity problem. Add a **query router** (extends the `analyze` node, ADR 0026): classify a query as *figure-seeking*, *narrative*, or *both*.
- **Figure path:** resolve `(entity, concept, period)` from the query → **exact SQL filter** on `financial_fact` (tenant-scoped) → the matching fact(s). No embedding, no ranking — a figure is looked up, not approximated.
- **Narrative path:** the existing hybrid doc retrieval (ADR 0004), unchanged.
- **Fusion:** a query that needs both (figure + explanation) joins the fact with its document evidence in one answer (Story 8.2 AC1). **Comparative queries** (period-over-period, entity-vs-entity) are computed **deterministically in SQL/code** from retrieved facts — never by the LLM (Story 8.2 AC4).

### 4. Answer composition — the LLM narrates, never computes
In the grounded-answer graph (ADR 0022), retrieved facts enter as **structured evidence** with their exact values; the model composes narrative and **quotes the figure verbatim from the fact**, citing `fact → document_version → period`. The grounding validator is extended with a **numeric check**: any number in the answer must match a retrieved fact's `value_numeric` (within unit/scale) or the claim is dropped. **Abstain** when the figure is unavailable or the `(entity, concept, period)` is ambiguous (Story 8.2 AC3) — never guess.

### 5. Evaluation — numeric accuracy (Epic 5 extension)
A new gold type: **figure questions with known values** (Story 8.3). Metrics: **exact-match / tolerance** on the numeric answer, and **figure-citation correctness** (right source + period). Regression-gated like faithfulness (ADR 0016), stored alongside existing eval runs. Deterministic + free (compare numbers) — a strong, cheap gate.

### Epic-8-MVP scope (and what's deferred)
**In:** point figures (single entity/concept/period), simple period-over-period + entity-vs-entity comparisons, SEC EDGAR XBRL subset, a `finance-sec` tenant (SEC data is US-government **public domain** — clean for the licensing gate, Story 6.5). **Deferred:** full XBRL taxonomy/dimensional modelling, calculation-linkbase validation, footnote-level reconciliation, non-XBRL statement formats, multi-currency normalization.

## Consequences
**Positive**
- Numbers are **retrieved + cited**, never generated → the financial-RAG failure mode (confident wrong figure) is designed out; abstention + numeric validation enforce it.
- **One datastore** preserved (ADR 0004): `financial_fact` is a Postgres table joined with documents in one query; citation chain + tenant isolation reuse the existing machinery.
- Reuses ports/adapters, the `IngestionJob` pipeline, `DocumentVersion` period/supersession semantics, the grounded-answer graph, and the Epic 5 eval harness — additive, not a parallel stack.
- Exact-match numeric eval is **deterministic + free** → a high-signal regression gate from day one.

**Negative / risks**
- A **new ingestion + retrieval path** to build and test (XBRL parsing is fiddly; taxonomies are large). Mitigated by the deliberately narrow Epic-8-MVP scope.
- The **query router** adds a classification step that can mis-route (figure vs narrative); must be measured + abstention-safe.
- **Period/dimension ambiguity** is the hard semantic problem (which "revenue", which segment, restated vs original) — handled by explicit `(entity, concept, period, dimensions)` keys + abstention on ambiguity, not heuristics.

**Neutral**
- Finance is a **different vertical** from the industrial-manuals MVP; this ADR activates Epic 8's requirements into the FR/NFR set per the epic-index process, it does not change MVP scope.

## Alternatives considered
- **Chunk the statements as text and retrieve figures via vector/LLM** — rejected: this is exactly how financial RAG hallucinates numbers (no exactness, no period semantics, LLM arithmetic). The whole point is a typed store.
- **A separate analytics datastore / warehouse (DuckDB, a column store)** — rejected at MVP: a second datastore (the run/sync/secure tax, ADR 0004) for a fact volume Postgres handles easily; revisit only at analytical scale.
- **Let the LLM compute comparisons** (growth %, deltas) — rejected: deterministic SQL/code is correct and auditable; the LLM narrates the computed result.
- **Full XBRL dimensional/taxonomy modelling up front** — rejected for MVP: huge surface for little initial value; start with point figures + simple comparisons, expand when measured demand appears.

## Revisit when
- Numeric-accuracy eval (Story 8.3) plateaus below target and analysis points at the fact model (missing dimensions) → extend the XBRL taxonomy coverage.
- Fact volume or comparative-analytics complexity outgrows Postgres aggregation → revisit a dedicated analytical store (tie to ADR 0027's datastore-when-forced discipline).
- A non-XBRL statement format (plain PDF 10-K tables) becomes primary → add a table-extraction adapter behind the same `StructuredExtractor` port.
