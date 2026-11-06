# IKIP — RAG Design Challenges (what makes RAG hard, and where IKIP handles it)

_Supporting appendix to `brief.md` and `prd.md`. Captures the difficulty dimensions that make a RAG system genuinely hard, useful and commercially valuable, and maps each to where IKIP addresses it (or why it is deferred). Companion to the source catalog in `data-sources.md`._

The point of this document: IKIP is **not** a generic "chat with PDF." It is a vertical industrial knowledge system designed around the retrieval problems below. Most of these are already encoded as requirements; the rest are consciously out of the initial scope (not forgotten).

---

## The difficulty dimensions

| # | Dimension | In IKIP MVP? | Where it is handled |
|---|-----------|--------------|---------------------|
| A | **Permission-aware retrieval & multi-tenancy** (per-customer isolation, object-level permissions, incremental sync, contradictory knowledge) | ✅ Core | FR8, FR21, NFR10 · Epic 6 (Stories 6.2, 6.3) · authorize-before-retrieve pattern · [ADR 0001](./adr/0001-vector-store-pgvector.md). Contradictory/conflicting knowledge → eval gold set (Story 5.1). |
| B | **Visual / multimodal documents** (scanned PDFs, tables, forms) | ⚠️ Partial in MVP; advanced → **planned (Epic 9)** | MVP: scanned PDFs + tables (FR3, FR4 · Story 2.3) + eval gold sets (Story 5.1). Advanced diagrams/schematics interpretation → **Epic 9 (post-MVP)**. |
| C | **Documents combined with structured data** (query exact figures from statements/XBRL) | 🟦 Planned (**Epic 8**, post-MVP) | Finance vertical. SEC EDGAR + XBRL source in `data-sources.md`; hybrid structured+unstructured retrieval in Epic 8. |
| D | **Temporal / version-aware retrieval** (valid-then vs valid-now; obsolete manuals still online) | ✅ Core | FR14 (applicable vs. obsolete) · `DocumentVersion` (revision, publication_date, effective_date, checksum) · Story 2.5 (versioning/supersession), Story 3.4 (version-aware filter) · eval gold set "outdated manuals" (Story 5.1). |
| E | **Retrieval benchmarks & evaluation datasets** (known answers → measure, don't demo) | ✅ Core | Epic 5 (Stories 5.1, 5.2) · NFR6 (Recall@5 ≥ 90%), NFR7 (citation ≥ 98%), NFR8 (groundedness ≥ 95%) · DocVQA / BEIR / RAGBench / IBM RAGWorkbench in `data-sources.md`. |

Legend: ✅ core MVP requirement · ⚠️ partially in scope · ❌ deliberately deferred.

---

## The capability questions a well-engineered RAG must answer

Each maps to an IKIP requirement so it is testable, not aspirational:

| Capability question | IKIP coverage |
|---------------------|---------------|
| Which exact document supports this answer? | FR16 citations (document/version/page/section) · NFR7 ≥ 98% resolve |
| Which model, jurisdiction, customer, document version does it apply to? | FR13 metadata filters · FR14 version-aware · `Equipment`/`DocumentVersion` data model · tenant scoping |
| What happens when two documents contradict each other? | Eval gold set "conflicting sources" (Story 5.1); version-awareness prefers applicable revision (FR14) |
| Can it retrieve from a table, image, or diagram? | Tables + scanned pages: FR4, Story 2.3. Diagrams/drawings: **deferred (P2)** |
| Can it say "I don't have enough evidence" instead of hallucinating? | FR17 abstention · Story 3.5 · Story 5.3 safety-abstention (100% pass gate) |
| Can you measure Recall@K, ranking, citation correctness, faithfulness? | Epic 5 (Stories 5.1–5.2) · NFR6/7/8 |
| Can you stop a user retrieving another customer's private documents? | FR21 authorize-before-retrieve · NFR10 zero cross-tenant disclosure (CI gate) · Story 6.2 |

---

## Promoted to planned post-MVP epics (sequenced after Epics 1–6)

These come from the broader RAG-mastery analysis. They are **not in the initial industrial-MVP scope (Epics 1–6)** but are now **committed, planned work** as dedicated post-MVP epics, rather than loose future notes. Each reuses the existing platform (ports & adapters, multi-tenant model, retrieval interfaces, evaluation harness).

| Item | Planned as | Stories |
|------|-----------|---------|
| **Enterprise internal connectors** (SharePoint, Confluence, support tickets, emails, meeting transcripts) | **Epic 7 — Enterprise Knowledge Connectors** | [`../prd/epic-7-enterprise-knowledge-connectors.md`](../prd/epic-7-enterprise-knowledge-connectors.md) |
| **Documents + structured-data querying** (exact financial figures, XBRL) | **Epic 8 — Structured-Data & Financial Retrieval** | [`../prd/epic-8-structured-data-financial-retrieval.md`](../prd/epic-8-structured-data-financial-retrieval.md) |
| **Advanced multimodal** (engineering drawings, schematics interpretation) | **Epic 9 — Advanced Multimodal Retrieval** | [`../prd/epic-9-advanced-multimodal-retrieval.md`](../prd/epic-9-advanced-multimodal-retrieval.md) |

> MVP remains Epics 1–6 (industrial manuals). Epics 7–9 are sequenced afterward; activate one by numbering its requirements into the FR/NFR set and running its stories through the normal SM→Dev loop.

> These map to the "four projects" learning path in the analysis: IKIP **is** project #1 (Technical Documentation Assistant) taken to production, **plus** the hard parts of project #4 (Enterprise Knowledge Platform — access control, tenant isolation, observability, evaluation, security, deployment). Projects #2 (banking/insurance compliance) and #3 (financial research) are **different verticals** reachable later via the same platform.

---

## Summary

- **In the plan already (implementation will cover):** permission-aware multi-tenant retrieval (A), scanned-PDF + table handling (B, partial), version-aware/temporal retrieval (D), evaluation benchmarks & metrics (E), abstention, citations, conflicting-source handling.
- **Planned post-MVP (Epics 7–9):** enterprise SaaS connectors (Epic 7), structured-data/XBRL querying (Epic 8), advanced drawing interpretation (Epic 9) — committed and sequenced after the core MVP.
- MVP scope (Epics 1–6) is unchanged; Epics 7–9 are the planned expansion path. Activate one by numbering its requirements into the FR/NFR set and running its stories through the normal SM→Dev loop.
