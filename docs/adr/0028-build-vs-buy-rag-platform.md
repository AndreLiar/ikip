# 0028. Build vs buy: why implement IKIP instead of adopting NotebookLM / AnythingLLM / a managed RAG

- **Status:** Accepted — build, with eyes open; the decision is **revisited per deployment** (a real customer may well be sent to a managed substrate).
- **Date:** 2026-11-15
- **Deciders:** Architect, PM (Mastère 2 thesis context — the *primary* stakeholder of the build is the author's competence, stated plainly below)
- **Related:** [ADR 0003](./0003-local-first-ports-and-adapters.md) (ports & adapters) · [ADR 0021](./0021-framework-boundary-langchain-langgraph-vs-data-plane.md) (reuse frameworks behind ports) · [ADR 0004](./0004-hybrid-retrieval-on-postgres.md) · [ADR 0016](./0016-rag-evaluation-custom-plus-ragas.md) (eval) · [ADR 0027](./0027-vector-storage-halfvec-now-qdrant-later.md) · concept [langchain-inventory](../learning/concepts/langchain-inventory.md)

## Context
Mature products already do document-intelligence/RAG well, so "why build IKIP from scratch?" is a fair and recurring question. Answering it honestly is itself an architecture decision — and a thesis is *weaker*, not stronger, if it pretends no alternative existed. The candidate off-the-shelf options, and where they land:

| Option | What it actually is | Strengths | Why it doesn't replace IKIP's stated goal |
|---|---|---|---|
| **Google NotebookLM** | Consumer/prosumer research assistant | Zero setup, excellent grounding + citations for *personal* use | No multi-tenancy, no API/SaaS substrate, data goes to Google, no isolation/SLA/audit — not a product you control |
| **GitHub/M365 Copilot** | Vendor-locked assistant over *its own* surface | Polished, enterprise SSO, maintained | Not a general document-intelligence platform you operate for third-party tenants; no auditable data-isolation guarantees |
| **AnythingLLM** | Open-source, self-hostable RAG w/ workspaces | Closest OSS analogue; local LLMs, multiple vector DBs | Workspace ≠ compliance-grade tenant isolation; eval/observability/safety-gate/injection-defense rigor is not built-in — you'd fork + extend heavily |
| **Managed RAG substrates** — Azure AI Search + OpenAI, Vertex AI Search, Bedrock Knowledge Bases, Glean, Vectara, Elastic | Buy-the-primitives platforms | Retrieval, chunking, scaling, security **mostly solved**; the rational "buy" for a shipping team | Solves most requirements — so the gap alone does **not** justify a from-scratch build; **learning does** |

Two framings matter before deciding:

1. **IKIP is not "from scratch" in the naive sense.** Per [ADR 0021](./0021-framework-boundary-langchain-langgraph-vs-data-plane.md) / [concept langchain-inventory](../learning/concepts/langchain-inventory.md), it reuses LangChain/LangGraph, Azure OpenAI, pgvector, Dagster, Presidio, Ragas. What is hand-built is the **architecture, orchestration, evaluation, security gates, and multi-tenant isolation** — i.e. the layer a *real* team also builds on top of bought primitives. The distance to AnythingLLM is "our architecture vs theirs", not "scratch vs mature".
2. **The domain requirements are real but mostly buy-able.** Hard, auditable tenant isolation (NFR10), citation-grounded answers with a resolvable chain (FR16), safety/abstention gates (Story 5.3/6.3), prompt-injection defenses (6.3), per-corpus eval regressions ([ADR 0016](./0016-rag-evaluation-custom-plus-ragas.md)), no vendor lock-in, cost control. NotebookLM fails most instantly; AnythingLLM is partial; **a managed substrate could close most of them too.** So requirements narrow the field but don't, by themselves, mandate building.

## Decision
**Build IKIP** — and be explicit that its primary justification is **learning + a reference architecture**, not a claim of market novelty.

1. **Primary rationale — build-to-learn + portfolio.** The deliverable is the author's demonstrated ability to *architect* a trustworthy, multi-tenant RAG platform (ADRs with alternatives, ports/adapters, measured evals, security gates, honest retrospectives), not a product that beats NotebookLM. Understanding the internals is what earns the right to later *buy well*.
2. **Secondary rationale — specific-requirement fit.** Where the domain genuinely needs it (auditable isolation, citation chain, abstention, injection defense, per-corpus eval gates), owning the data plane behind ports ([ADR 0003](./0003-local-first-ports-and-adapters.md)) gives control a managed black box doesn't — *and* keeps a clean exit to managed components.
3. **Buy the primitives, build the differentiators.** Do not reimplement embeddings, LLMs, or an ANN index. Reuse frameworks behind business ports ([ADR 0021](./0021-framework-boundary-langchain-langgraph-vs-data-plane.md)); the ports make "swap our pgvector arm for Qdrant" ([ADR 0027](./0027-vector-storage-halfvec-now-qdrant-later.md)) or "swap retrieval for Azure AI Search" a contained change, not a rewrite.
4. **Record the counterfactual.** For a real customer shipping next quarter with a small team, the honest recommendation is often *assemble a managed substrate* (e.g. Azure AI Search + OpenAI) and build only the thin differentiating slice — **not** IKIP. This ADR exists so that recommendation is on the record.

## Consequences
**Positive**
- Deep, transferable competence across the full stack; the judgment to evaluate/integrate the bought options well.
- A portfolio artifact whose **honesty about build-vs-buy reads as maturity** to examiners and employers.
- Ports/adapters mean the build is not a dead end: managed substrates can be adopted incrementally behind the same seams.

**Negative / risks**
- **Opportunity cost**: engineering spent on plumbing a managed service would provide for free. Mitigated by (3) — buy primitives.
- **Maintenance burden** a vendor would otherwise carry (upgrades, scaling, security patches).
- **Feature lag** vs well-funded products (NotebookLM's UX, managed search's scale).

**Neutral**
- The "build" boundary is deliberately narrow (data plane + orchestration + eval + security), not "reinvent the model".

## Alternatives considered
- **Adopt NotebookLM** — rejected for a multi-tenant SaaS: no isolation/API/residency control; great only as a personal-research baseline to compare grounding against.
- **Fork AnythingLLM** — viable and the closest shortcut; rejected as the *primary* path because the learning goal wants the architecture built, not inherited, and its isolation/eval/security rigor would need heavy extension anyway. **Worth studying as prior art.**
- **Managed RAG substrate (Azure AI Search + OpenAI / Vertex / Bedrock KB)** — the correct **buy** answer for a product-first team; kept explicitly as the recommended path for a real customer and as IKIP's own future exit behind the retrieval port.
- **Upgrade nothing, demo a notebook** — rejected: proves nothing about operating a trustworthy platform.

## Revisit when
- **A real customer/deployment appears** → re-run this decision for *them*; default to assembling a managed substrate unless an auditable-isolation/residency/lock-in requirement tips it back to owning the data plane.
- **The learning goal is met** → further effort should shift from building plumbing to the differentiating slice (domain retrieval quality, agentic reformulation — [Epic 10](../prd/epic-10-agentic-rag.md)).
- **A managed substrate adds a capability we hand-built** (e.g. native tenant-isolated hybrid search with citations) → adopt it behind the existing port and delete our version.
