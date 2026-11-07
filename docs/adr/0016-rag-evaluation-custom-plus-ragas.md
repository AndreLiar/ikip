# 0016. RAG evaluation: custom deterministic harness + Ragas, compared

- **Status:** Accepted
- **Date:** 2026-11-07
- **Deciders:** Architect, PM
- **Related:** FR29, FR30 · NFR6, NFR7, NFR8, NFR9 · Epic 5 (Stories 5.1, 5.2, 5.5) · relates to [ADR 0007](./0007-pluggable-llm-client-azure-openai.md), [ADR 0013](./0013-llmops-observability-otel-langfuse.md)

## Context
Epic 5 needs measurable RAG quality — Recall@K, citation correctness, groundedness/faithfulness, answer relevancy (NFR6–NFR9). The original plan said "pytest + custom gold datasets + custom groundedness check", which **omitted [Ragas](https://github.com/explodinggradients/ragas)** — the de-facto open-source RAG evaluation framework (metrics: `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`, `answer_correctness`, …). Hand-rolling LLM-judged metrics duplicates a mature library and risks weaker, less-comparable metrics.

Separately, there is a genuine engineering question: **do a hand-rolled harness and Ragas agree?** For a thesis/portfolio, comparing them is itself a valuable, defensible result.

## Decision
Use **both**, with a clear split, and **compare them** as a deliverable:

1. **Custom deterministic metrics (own code)** — `Recall@K` and **citation resolution** (does the cited document/version/page exist and contain the claim). No LLM needed → fast, free, fully reproducible. Owns NFR6, NFR7.
2. **Ragas (LLM-judged metrics)** — `faithfulness` (→ groundedness, NFR8), `answer_relevancy`, `context_precision`, `context_recall`. Judge LLM = Azure OpenAI via the `LLMClient` ([ADR 0007](./0007-pluggable-llm-client-azure-openai.md)); scores pushed to **Langfuse** ([ADR 0013](./0013-llmops-observability-otel-langfuse.md)).
3. **Comparison harness** — both run on the same gold dataset (Story 5.1); we report **agreement/divergence** (e.g., correlation between custom-groundedness and Ragas-faithfulness), **cost**, and **stability/variance across runs**, to justify which metric set gates releases.

Both are orchestrated by **pytest** and wired into CI gates (Story 5.5): deterministic metrics run on every push; **LLM-judged (Ragas) metrics run on a bounded sample** with thresholds + tolerance (cost/non-determinism control), and in full on demand / nightly.

## Consequences
**Positive**
- Standard, well-tested RAG metrics (Ragas) instead of bespoke ones; stronger and more comparable to the literature.
- Deterministic metrics stay fast/free/reproducible for the per-push gate.
- The **custom-vs-Ragas comparison** is a concrete thesis deliverable (which metric is trustworthy, cheaper, more stable).
- Ragas integrates with Azure OpenAI (judge) and Langfuse (score tracking) — fits the existing stack.

**Negative / risks**
- Ragas' LLM-judged metrics **cost tokens** and are **non-deterministic** → unsuitable for a strict per-push gate; mitigated by sampling + tolerance + nightly full runs.
- Two metric systems to maintain; mitigated because the custom side is small (Recall@K, citation) and Ragas is a library.
- Judge-LLM bias — Ragas scores depend on the judge model/version; pin and version it (Story 5.5).

**Neutral**
- Ragas needs embeddings/LLM config already present (Azure OpenAI).

## Alternatives Considered
- **Custom harness only (original plan):** full control, but reinvents mature metrics and lacks comparability to published RAG benchmarks. Rejected as the sole approach.
- **Ragas only:** standard metrics, but all LLM-judged metrics are costly/non-deterministic for CI, and pure retrieval metrics (Recall@K) don't need an LLM. Rejected as the sole approach.
- **Other eval libs (TruLens, DeepEval, promptfoo):** viable; Ragas chosen for RAG-specific metric maturity + Langfuse/Azure integration. Revisit if a gap appears.

## Revisit When
- The comparison shows one approach is clearly superior for IKIP → consolidate on it (keep the other as a cross-check).
- Ragas judge-LLM cost/variance makes even sampled CI gates impractical → move Ragas fully to nightly, gate only on deterministic metrics.
- A different eval framework offers decisive RAG-metric or integration advantages.
