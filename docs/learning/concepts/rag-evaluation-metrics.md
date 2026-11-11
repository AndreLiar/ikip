# Concept — RAG evaluation metrics (how to read IKIP's eval numbers)

Write-once reference for the numbers produced by `python -m ikip_common.eval {run,ragas,compare}`. Used by [[MISSION-029]], [[MISSION-031]], [[MISSION-032]]. Decision context: [ADR 0016](../../adr/0016-rag-evaluation-custom-plus-ragas.md).

## Two families, on purpose

| | Deterministic (our `metrics.py`) | Ragas (LLM-judged) |
|---|---|---|
| Cost | free | tokens (judge LLM) |
| Reproducible | yes (bit-for-bit) | no (non-deterministic; measure variance) |
| Gates | **every push** | **nightly / bounded sample** |
| Sees | citations, ranking, behavior | **semantic entailment / relevance** |

They are complementary: deterministic metrics are a fast, free floor; Ragas catches meaning-level failures the deterministic ones are blind to. ADR 0016 predicted this; `eval compare` measures it.

## Deterministic metrics (`eval run` aggregate)

- **`recall_at_k`** — did retrieval surface the relevant chunks in the top-K? `|relevant ∩ topK| / |relevant|`. No relevant ids (abstain case) → 1.0 (vacuous). *Measures retrieval, not the answer.*
- **`citation_resolution`** — do the answer's cited chunk-ids resolve to chunks that were actually retrieved? Guards against fabricated references.
- **`citation_grounding_coverage`** — fraction of claims carrying ≥1 **resolvable** citation. ⚠️ **Presence only, NOT truth**: a claim that cites a real chunk scores 1.0 even if the claim cherry-picks or contradicts other evidence. This is the metric's deliberate blind spot (entailment is Ragas' job).
- **`behavior_conformity`** — fraction of cases whose behavior (answered vs abstained) matches the gold's `expected_behavior`. The single most honest "did it do the right thing" number.
- **`abstention_rate`** — fraction that abstained. Context for conformity (is it abstaining on the *right* cases?).
- **`latency_ms_p50/p95`**, **`estimated_cost_usd_total`** — operational cost of the run.

## Ragas metrics (`eval ragas`)

- **`faithfulness`** — are the answer's claims **entailed by the retrieved context** (taken as a whole)? Catches hallucination AND internal contradiction. *This is the LLM analogue of our coverage — but semantic.*
- **`answer_relevancy`** — does the answer actually address the question?
- **`context_precision`** — were the retrieved chunks relevant (low noise)?
- **`context_recall`** — did the context cover the reference answer (`ground_truth`)?
- **`answer_correctness`** — is the answer semantically equal to the `ground_truth`?

Ragas returns **NaN** for a metric it can't judge (e.g. `faithfulness` on an abstained/empty answer) → our code excludes NaN from means and compares answered-cases-only.

## Comparison report (`eval compare`)

- **`agreement_rate`** — fraction of (answered) cases where custom coverage and Ragas faithfulness land on the same side of a 0.7 threshold.
- **`mean_abs_difference`** — average `|custom − ragas|` per case.
- **`pearson_correlation`** — linear correlation of the two series. **`None` when a series has zero variance** (e.g. custom coverage is 1.0 everywhere → a constant can't be correlated). Common on small/clean gold sets.
- **`divergent_cases`** — cases where the two metrics disagree by more than a tolerance. **These are the gold** — they point at meaning-level failures the cheap metric missed.
- **`ragas_variance`** — population variance of each Ragas mean across repeated runs. Near 0 ⇒ the judge is stable here ⇒ safe-ish to trust a single run.
- **`ragas_cost_usd`** — estimated judge cost.

## Worked example — the conflicting-sources case (real, 2026-11-11)

Question: *"max operating pressure of vessel V-3?"*. Two **current** sources: `8 bar` and `10 bar`. Gold expects **abstain** (surface the conflict).

- Before the v2 prompt fix, the system answered **"10 bar [E1]"**.
  - `citation_grounding_coverage = 1.0` — the claim cites E1 (which does say 10 bar). The metric only checks the citation **exists**, so it is happy.
  - `faithfulness = 0.0` — Ragas checks the claim against the **whole** context, which also contains "8 bar". The context contradicts itself on this point → the claim isn't reliably entailed → 0.0.
  - `behavior_conformity` dropped (answered, expected abstained).
  - In `compare`: **1 divergent case** (coverage 1.0 vs faithfulness 0.0) + agreement 0.8. The divergence localised a real defect the free metric couldn't see.
- **Fix** (prompt config **v2**, promoted through the 5.5 gate): instruct the model to abstain and name the conflict when ≥2 **current** sources disagree (a superseded revision is NOT a conflict). After v2: the case abstains, `behavior_conformity = 1.0`, and it drops out of the faithfulness comparison (no answer to judge) → no divergence.

**Takeaway**: coverage = "is there a citation?"; faithfulness = "is the claim true given the evidence?". When they disagree, trust faithfulness to find the bug, then fix with a gated, versioned prompt change.
