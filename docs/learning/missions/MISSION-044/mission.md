# MISSION-044 — Measure Stage-1 auto-merge (ADR 0029): does parent/child context actually help?

- **Mode:** Autonome (wire the measurement; the live A/B run is a gated, paid follow-up)
- **Date:** 2026-11-15
- **Related:** [ADR 0029](../../adr/0029-hierarchical-parent-child-chunking.md) (Stage-1 design+impl) · [ADR 0016](../../adr/0016-rag-evaluation-custom-plus-ragas.md) (eval) · [MISSION-043](../MISSION-043/mission.md) (NTRS weakness this targets) · concept [chunking](../concepts/chunking.md)

## Objective
Stage-1 auto-merge (parent/child retrieval) shipped **opt-in and unmeasured** (PR #87). A feature
that isn't measured is a hypothesis, not an improvement. Wire an **A/B**: run the same gold set
with `auto_merge` **off** (baseline) vs **on** (Stage 1) and report whether the wider parent
context improves answers — on **NTRS**, the corpus MISSION-043 proved weak (large PDFs, detail
questions).

## What was wired (this mission)
- `make_hybrid_retrieve(auto_merge=…, parent_max_tokens=…)` already applies `expand_to_parents`
  (ADR 0029). Threaded that flag through the eval CLI: `eval run`, `eval ragas`, `eval compare`
  now take **`--auto-merge`** (+ `--parent-max-tokens`), and the written report records
  `config.auto_merge` so off/on runs are distinguishable.
- Test `test_make_hybrid_retrieve_applies_automerge_only_when_enabled` proves the flag threads
  through to `expand_to_parents` (no network).

## Method (the A/B — commands)
NTRS tenant `c0f90000-0000-4000-8000-0000000000a1`, gold `eval-results/gold_mini.json`.

```bash
# deterministic (free-ish; grounded_answer = Azure chat): baseline then Stage-1
uv run --group embeddings --group doctor python -m ikip_common.eval run \
  --gold eval-results/gold_mini.json --tenant <NTRS> --out eval-results/ab/base
uv run --group embeddings --group doctor python -m ikip_common.eval run \
  --gold eval-results/gold_mini.json --tenant <NTRS> --auto-merge --out eval-results/ab/merge

# LLM-judged (the REAL signal; Azure judge → costs $, use --sample/--budget-usd)
uv run --group ragas --group embeddings python -m ikip_common.eval ragas \
  --gold eval-results/gold_mini.json --tenant <NTRS> --sample 5 --budget-usd 0.50 --out eval-results/ab/base
uv run --group ragas --group embeddings python -m ikip_common.eval ragas \
  --gold eval-results/gold_mini.json --tenant <NTRS> --auto-merge --sample 5 --budget-usd 0.50 --out eval-results/ab/merge
```

## The metric caveat (read before trusting the numbers)
**`recall_at_k` is the WRONG headline metric for this change.** It compares the *child* `chunk_id`s
returned. Auto-merge **dedups** (several child hits in one section collapse to one parent), so it
returns *fewer distinct child ids* — recall@k can **drop** even though the merged parent text now
*contains* those relevant chunks. Judge the context win by:
- **Ragas `faithfulness`** — did groundedness hold (did wider context cause drift)?
- **Ragas `context_recall` / `answer_correctness`** — did the parent context let the answer cover the ground truth?
- **latency_ms / estimated_cost** — parents are bigger → more tokens → expect cost/latency **up**.

So the honest success criterion: **faithfulness holds, correctness/context-recall rise, at an
acceptable cost increase** — not "recall@k went up".

## Results
_Pending the live A/B run (gated: paid Azure judge). Fill from `eval-results/ab/*`._

| metric | baseline (off) | Stage-1 (on) | Δ | read |
|---|--:|--:|--:|---|
| faithfulness | — | — | — | should **hold** (≈ no drop) |
| answer_correctness | — | — | — | hoped **up** (more context) |
| context_recall | — | — | — | hoped **up** |
| recall_at_k | — | — | — | may **drop** (dedup artifact — not the point) |
| latency_ms p50 | — | — | — | expected **up** |
| est_cost_usd total | — | — | — | expected **up** |

## Next
1. Run the live A/B (bounded `--sample`, `--budget-usd` cap) and fill the table.
2. If correctness/context-recall rise and faithfulness holds → propose flipping `auto_merge` default on (and wire it into the ask path + a per-corpus regression gate, ADR 0016).
3. If not → keep opt-in; revisit `parent_max_tokens` or move to Stage-2 (smaller children, gated on Qdrant, ADR 0027).
