# 0032. Memory & context engineering — serve retrieval, never the answer

- **Status:** Accepted — all three layers implemented (L1 conversational contextualization #119; L2 long-term memory `ikip_common.user_memory` #120; L3 context engineering `ikip_common.context_engineering` #121). Each shipped opt-in + grounding-safe per the decision below; the context-engineering knobs remain opt-in until A/B measurement promotes one.
- **Date:** 2026-11-16
- **Deciders:** Architect, PM
- **Related:** [ADR 0022](./0022-grounded-answer-langgraph-gpt5-mini.md) (grounded answer) · [ADR 0026](./0026-agentic-rag-evolution.md) (query analysis/reformulation) · [ADR 0004](./0004-hybrid-retrieval-on-postgres.md) / [ADR 0016](./0016-rag-evaluation-custom-plus-ragas.md) · concept [grounded-answers](../learning/concepts/grounded-answers.md) · [MISSION-044](../learning/missions/MISSION-044/mission.md) (context is a measured trade-off) · FR16 (citations) · NFR10 (tenant isolation)

## Context
The RAG pipeline is solid but lacks three things common in modern AI systems: **conversational memory** (use the thread so "and Q2?" resolves), **long-term memory** (per-user/tenant preferences + entities across sessions), and **context engineering** (budget/order/compress the retrieved context).

### What already exists (don't reinvent — reuse these seams)
A fair amount of the groundwork is present; the gap is that none of it is *used in the answer loop*:

| Brique existante | Où | Ce qu'elle apporte déjà |
|---|---|---|
| **Historique conversationnel** | `Conversation` + `ConversationMessage` + `answer_feedback` (MISSION-025) | l'historique du fil est **stocké** (par tenant + user) — la matière première de la mémoire conversationnelle |
| **Éval multi-tours** | `eval/multiturn.py` (MISSION-034) | mesure déjà si un follow-up (pronoms/ellipse) est bien traité — **le mètre pour prouver** que la contextualisation aide |
| **Cache de réponses** | answer cache (MISSION-018) | une forme de mémoire : réutilisation exacte, clé tenant/version/epoch (abstention-preserving) |
| **Context assembly (base)** | graphe grounded-answer (blocs `[E1]…`) + fusion Epic 8 (figure+doc) | déjà du *context engineering* : assemblage d'évidence structurée → le point d'insertion de #3 |
| **Reranker port + RRF** | `Reranker` (Protocol) + `IdentityReranker` défaut, `reciprocal_rank_fusion` (`llm/hybrid.py`) | le **seam** pour le re-ranking de contexte existe — il suffit d'y brancher un cross-encoder |
| **`analyze` node** | `llm/answer.py` (ne fait que `.strip()` aujourd'hui) | le **point d'accroche** de la contextualisation de requête (#1) et de la reformulation (ADR 0026) |

Donc #1 (contextualisation) se branche sur `analyze` + `ConversationMessage`, #3 (reranking) sur le `Reranker` port — rien à réinventer, et l'`eval/multiturn` + les gold gates servent à **mesurer**.

The non-negotiable constraint is the product's core promise (ADR 0022): **every claim resolves to a retrieved citation, or the system abstains**. The danger with memory is obvious: a "remembered fact" injected into the answer is an **uncited, possibly-stale claim** that bypasses grounding. And MISSION-044 already measured that *"more context" is a trade-off, not a free win* — so context engineering must be **measured, not assumed**.

## Decision
One principle governs all three: **memory and context shape WHAT we retrieve and HOW we assemble it — never WHAT we claim.** The citation/abstention guarantee is invariant; memory is **not** evidence. Concretely, three layers, all upstream of or around retrieval, none touching the answer contract:

### 1. Conversational memory (in-loop) — contextualize the query
At the `analyze` node (ADR 0022/0026), rewrite a follow-up into a **standalone query** using the recent thread (`ConversationMessage` history): resolve pronouns/ellipsis ("and Q2?" → "…Apple Q2 FY2023 revenue"). This changes **only the retrieval query**, not the evidence or the answer — so it **strengthens** grounding (better retrieval) rather than threatening it. Opt-in, bounded history window, **A/B'd on the existing `eval/multiturn`**. (Lower-risk than the already-tried query-rewrite because it uses real thread context, and we can measure it.)

### 2. Long-term memory — enrich retrieval, with a hard garde-fou
A per-(tenant,user) memory store of **preferences** (units, language, equipment scope) and **entities** (the filers/assets this user works with). It is used **only** to:
- **bias/filter retrieval** (e.g. default the equipment/version filter, resolve "our usual supplier" to an entity), and
- **personalize presentation** (language/units).

It is **never** a source of answer content. Hard garde-fou, enforced structurally: long-term memory feeds the *query/filters*, and the grounding validator + citation resolution are unchanged — a claim with no retrieved citation is still dropped/abstained. Memory entries are **not** passed as evidence blocks to the generator. Tenant/user-scoped (NFR10); user-visible + editable (it's their memory); retention-governed (Story 6.5).

### 3. Context engineering — budget, rerank, compress (all measured)
Make the assembled context deliberate, not "top-k raw", behind the existing seams and **A/B-gated** (faithfulness + recall, ADR 0016):
- **Token budget** for the evidence block (don't overflow / dilute).
- **Reranking**: activate a real **cross-encoder behind the existing `Reranker` port** (identity → cross-encoder) to order by true relevance before the budget cut.
- **Compression/dedup**: drop near-duplicate retrieved chunks; optionally summarize long evidence — but a summary used for *generation* must still carry the **original chunk citations** (never cite the summary).
- **Ordering**: mitigate "lost-in-the-middle" (strongest evidence at the edges).

Each knob ships **opt-in and A/B'd** — MISSION-044 showed context changes can hurt, so none becomes default without measured ≥-baseline faithfulness + a recall/correctness win.

## Consequences
**Positive**
- Memory & context become real capabilities **without weakening the grounding guarantee** — the invariant ("claim ⇒ citation, else abstain") is untouched by design.
- Conversational memory directly fixes a measured gap (multi-turn follow-ups) and *improves* retrieval.
- Reuses existing seams: `analyze` node, `Reranker` port, `Conversation` model, `eval/multiturn` + the gold gates.
- Long-term memory is inspectable/editable by the user (trust) and tenant-scoped (NFR10).

**Negative / risks**
- **The temptation to let memory answer** is the central risk; mitigated structurally (memory → query/filters only; generator sees only retrieved evidence) + tested (an adversarial test: a remembered "fact" must never appear as an uncited claim).
- Long-term memory is **stateful personalization** → staleness, privacy, retention surface (governed by Story 6.5; user-editable).
- Context-engineering knobs can regress quality (MISSION-044) → each is opt-in + A/B-gated, never assumed.
- Query contextualization can mis-resolve a follow-up → abstention-safe + measured on multiturn.

**Neutral**
- These are **request-time** concerns (ADR 0002 request-time plane); no change to the build-time KB pipeline.

## Alternatives considered
- **Feed conversation/long-term memory straight into the generator as context** — rejected: that's exactly how memory becomes an uncited claim and breaks grounding. Memory informs *retrieval*, not generation.
- **Full agentic multi-step memory/retrieval now** (ADR 0026) — deferred: bigger, and the in-loop query contextualization + context engineering are the smaller, measurable first steps; agentic iteration builds on them.
- **Semantic/vector long-term memory** (embed past turns, retrieve them as context) — a form of #1/#2 but risks re-injecting stale "answers"; if adopted, memory hits must be treated as *query signal*, not evidence.
- **Ship context knobs as defaults** — rejected: MISSION-044 proved context changes can regress; opt-in + A/B is mandatory.

## Revisit when
- `eval/multiturn` shows conversational contextualization materially lifts follow-up quality → make it default (with a faithfulness gate).
- A reranker/compression A/B holds faithfulness ≥ baseline AND lifts recall/correctness on the gold → promote it from opt-in to default.
- Long-term memory demand grows (cross-session personalization) → implement the store + the adversarial grounding guard first, then the retrieval-biasing.
- These foundations are in place → agentic iterative retrieval (ADR 0026) becomes the next layer on top.
