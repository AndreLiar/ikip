# MISSION-032 — Unblock Ragas + first real custom-vs-Ragas comparison (Epic 5, Story 5.2)

**Mode:** Autonome (resolve the MISSION-031 live blocker) + knowledge transfer.
**Objective:** make `eval ragas/compare` actually run against the Azure judge and produce the thesis artifact — the custom-vs-Ragas comparison on the seeded corpus.
**Maps to:** Epic 5 / Story 5.2 (the live half that was `[blocked]`).

## The blocker and the fix
`ragas` hard-imports `from langchain_community.chat_models.vertexai import ChatVertexAI` at module load. `langchain-community >= 0.4` **removed** that path, so any ragas import raised `ModuleNotFoundError`. Fix: pin **`langchain-community>=0.3,<0.4`** in the `ragas` group — 0.3.x still ships `chat_models.vertexai` and resolves cleanly with our `langchain-core` (which moved to **1.x** in the process). All graph/eval tests pass under langchain-core 1.x, so the upgrade is absorbed (no code change needed for our LangGraph answer flow).

## Code fixes found by the live run
- **NaN handling.** Ragas returns `NaN` for a metric it can't judge — e.g. `faithfulness` on an **abstained** (empty) answer. One NaN was poisoning `mean_abs_difference` + variance. Fixes: `_means` excludes NaN; the `compare` CLI pairs **only ANSWERED cases** (abstention correctness is covered by `behavior_conformity` + the safety gate, not by groundedness-vs-faithfulness). Test: `_means` excludes NaN.

## First real comparison (2026-11-11, Azure judge, 2 runs, seeded corpus)
`eval seed` → `eval compare --runs 2` on `failure_modes.resolved.json`:

| answered case | custom coverage | Ragas faithfulness |
|---|---|---|
| equipment-identifier (fault E42) | 1.00 | 1.000 |
| outdated-manual (current rev B) | 1.00 | 1.000 |
| **conflicting-sources** | 1.00 | **0.000** |
| table lookup | 1.00 | 1.000 |
| scanned/OCR | 1.00 | 1.000 |

- **agreement = 0.80**, mean-abs-diff = 0.20, **1 divergent case: `conflicting-sources`**.
- Ragas **run-to-run variance ≈ 0** (faithfulness 0.0, others ≤ 6e-4) → stable here; cost ≈ **$0.006**.
- The divergence is the whole point of the comparison: deterministic coverage says "every claim has a resolvable citation" (1.0), but Ragas faithfulness says the answer is **not entailed by the evidence** (0.0) — the system picked one value for a vessel's max pressure where two current sources conflict, instead of surfacing the conflict. This **coincides with the `eval run` signal** (`behavior_conformity = 0.875`, the same case), so two independent metrics flag it. Artifact: `evidence/comparison.live.json`.

## Thesis conclusion (which metric gates)
Deterministic metrics (free, reproducible, 0 variance) gate **every push**; Ragas faithfulness catches **entailment gaps the deterministic coverage cannot see** (the conflicting-sources case) — run it **nightly / on a bounded sample**, not per push (cost + the judge is non-deterministic, though low-variance here). This is precisely the split ADR 0016 predicted, now **measured** rather than asserted.

## Verification
- ruff + format ✓; `pytest apps packages services` → 224 passed / 44 skipped under langchain-core 1.x; broad embeddings suite (answer graph, hybrid, retriever, harness, compare, safety, ragas) → 34 passed.
- Live: `eval compare --runs 2` produced the NaN-free `comparison.live.json` above. **[verified live]**

## Deliverables
- `pyproject.toml` (`langchain-community<0.4` pin + rationale comment); `uv.lock`.
- `eval/ragas_eval.py` (`_means` NaN-safe); `eval/__main__.py` (`compare` pairs answered-only, NaN-safe).
- `tests/test_ragas_eval.py` (`test_means_exclude_nan`); `evidence/comparison.live.json` (under MISSION-029).

## Follow-ups (noted)
- Investigate/fix the `conflicting-sources` behavior (should surface the conflict or abstain) — a retrieval/answer-policy improvement, now backed by two metrics.
- Migrate ragas metric imports to `ragas.metrics.collections` before ragas v1.0 (current imports are deprecated-but-working).
- Wire the nightly `ragas-eval.yml` to a seeded staging tenant so the comparison refreshes automatically.

## Concepts
Completes [[MISSION-029]] (Ragas) + [[MISSION-031]] (seed/live run). Measures the ADR 0016 custom-vs-Ragas split.
