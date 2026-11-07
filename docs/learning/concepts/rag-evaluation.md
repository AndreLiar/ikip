# Concept — RAG evaluation: the deterministic baseline

_Write-once concept note. First used by Story 3.6. Decision: [ADR 0016](../../adr/0016-rag-evaluation-custom-plus-ragas.md). Follows [grounded-answers](./grounded-answers.md)._

## Why measure before building the UI
"Is the RAG any good?" must be a **number**, not a vibe — otherwise you can't tell a change improved it or broke it. Story 3.6 builds the **deterministic baseline**: metrics that need **no LLM**, so they're fast, free, reproducible, and safe to run on every push. LLM-judged metrics (Ragas faithfulness) are costly + non-deterministic → Epic 5.

## The two kinds of metric (and why 3.6 only does one)
| | Deterministic (Story 3.6) | LLM-judged (Epic 5, Ragas) |
|---|---|---|
| Examples | Recall@K, citation resolution, citation-grounding coverage, behavior conformity, latency, est. cost | faithfulness (entailment), answer relevancy, context precision |
| Needs an LLM? | ❌ | ✅ (judge model) |
| Reproducible? | ✅ bit-stable (quality metrics) | ❌ varies per run |
| CI role | per-push gate | sampled / nightly |

## The metrics (deterministic)
- **Recall@K** — of the *relevant* chunks (gold), how many appear in the top-K retrieved? K is explicit/configurable. Pure retrieval signal.
- **Citation resolution** — do the answer's cited chunk ids resolve to chunks that were actually retrieved? (provenance integrity).
- **`citation_grounding_coverage`** — fraction of claims carrying ≥1 resolvable citation. **Deliberately named this, not `faithfulness`**: it checks evidence is *present and resolvable*, **not** that it *semantically entails* the claim. That entailment check is LLM-judged (Epic 5).
- **Behavior conformity** — did the system answer vs abstain as the gold case expects? (abstention correctness).
- **Latency p50/p95** and **estimated cost/answer** — operational signals (cost is a char/4 estimate; real FinOps is Epic 5).

> The crucial honesty: **resolution ≠ entailment.** A claim can cite a real retrieved chunk that doesn't actually support it. Deterministic metrics catch missing/fabricated/ dangling citations; they can't catch a *plausible-but-unsupported* claim. Don't oversell coverage as faithfulness.

## Separate retrieval from answer
A bad Recall@K doesn't imply bad generation, and vice-versa. The harness records **both** per case (retrieved ids + recall on the retrieval side; citation/grounding/behavior on the answer side) so a regression is attributable. It captures the retrieval the graph actually used (no double retrieval) via a wrapping callable.

## Reproducible + stored: three artifacts
Runs are driven by the harness over a **versioned gold fixture** with a `FakeChatClient` (no network) for the per-push gate; live runs use the CLI (`python -m ikip_common.eval run`). Results are stored as **three distinct artifacts** so a bad run never silently becomes the reference:
- `runs/<timestamp>.json` — immutable history (config, dataset version, commit SHA, aggregate + per-case).
- `latest.json` — the most recent run.
- `baseline.json` — the **approved** reference; only set by explicit `promote` (never auto-written).

Regression = a higher-is-better metric in `latest` fell more than a tolerance below `baseline` (`check` exits non-zero). `gold_set_version` distinguishes a *retrieval/generation* regression from a *corpus change*.

## `evaluation_case` (the gold set)
Tenant-scoped rows: stable `case_key` within a `gold_set_version`, `question`, `expected_behavior` (answered/abstained, stored as a plain String — no DB enum trap), `relevant_chunk_ids`. The gold set is the ground truth Recall@K and behavior conformity are measured against.

## Rules to remember
1. Deterministic metrics only in 3.6 (fast/free/reproducible); Ragas (LLM-judged) is Epic 5.
2. **Resolution ≠ entailment** — name it `citation_grounding_coverage`, never `faithfulness`.
3. Separate retrieval vs answer metrics so regressions are attributable.
4. No LLM in the per-push gate: `FakeChatClient` + versioned fixtures.
5. Three artifacts; `baseline.json` is promoted **manually**, never auto.
6. Latency is wall-clock → excluded from the bit-reproducibility contract.

## Related
- Decision: [ADR 0016](../../adr/0016-rag-evaluation-custom-plus-ragas.md) (custom + Ragas, compared).
- Concepts: [grounded-answers](./grounded-answers.md) · [hybrid-retrieval](./hybrid-retrieval.md) · [retrieval](./retrieval.md) · [multi-tenancy](./multi-tenancy.md).
- Next: Epic 5 adds Ragas (faithfulness/relevancy), the custom-vs-Ragas comparison, Langfuse score tracking, and CI gates.
