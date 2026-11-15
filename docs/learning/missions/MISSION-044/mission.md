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

## Results (live Ragas, NTRS, n=5 silver gold, 2026-11-15)
Ran the A/B via `eval ragas … [--auto-merge]` (budget-capped). Azure judge.

| metric | baseline (off) | Stage-1 (on) | Δ | read |
|---|--:|--:|--:|---|
| **faithfulness** | **1.000** | **0.889** | **−0.111** | ⚠️ grounding slipped (one claim drifted) |
| **answer_correctness** | 0.463 | **0.544** | **+0.081** | ✅ wider context → more correct |
| answer_relevancy | 0.476 | 0.519 | +0.043 | ✅ slightly more on-point |
| context_precision | 0.567 | 0.550 | −0.017 | parents carry more non-essential text (expected) |
| context_recall | 0.600 | 0.600 | 0.000 | relevant content was already retrieved; merge adds surrounds, not new coverage |
| recall_at_k | n/a | n/a | — | gold has no `relevant_chunk_ids`; and it's the wrong metric here anyway |

## Follow-up — parent-window sweep (does a smaller window buy back trust?)
Hypothesis: a **smaller** `parent_max_tokens` = less context dilution → faithfulness recovers while
keeping the correctness gain. Re-ran ON at **700** tokens (vs the 1200 default):

| metric | off | on @1200 | on @700 |
|---|--:|--:|--:|
| **faithfulness** | **1.000** | 0.889 | **0.825** |
| answer_correctness | 0.463 | 0.544 | **0.562** |
| answer_relevancy | 0.476 | 0.519 | **0.605** |
| context_precision | 0.567 | 0.550 | 0.550 |
| context_recall | 0.600 | 0.600 | 0.600 |

**Hypothesis rejected.** The smaller window did **not** recover faithfulness (0.825 ≤ 0.889 — no
gain, and within n=5 judge noise either way), while correctness/relevancy kept drifting up. So the
grounding cost is **not** a "too much context" artifact fixable by shrinking the parent — showing
*any* merged parent context on this corpus costs some grounding. The robust signal across both
windows is **ON-vs-OFF**: auto-merge trades ~one claim of faithfulness for better correctness,
independent of window size. Parent-size tuning is **not** the lever.

## Discovery — it's a **trade-off, not a win**
Stage-1 auto-merge did exactly what the ADR predicted on both sides: **more context lifted
answer correctness (+8 pts) and relevancy (+4 pts), but diluted grounding — faithfulness fell
1.00 → 0.89.** On a safety-first system that *gates on faithfulness*, a −0.11 is a regression in
the one property we refuse to trade. So the measured verdict is **do NOT flip `auto_merge` on by
default yet** — the correctness gain is real but not free.

**Honest caveats:** n=5, **silver** gold (LLM-from-corpus), LLM-judge variance, and `ntrs-3` is a
degenerate positional-lookup question (MISSION-043) that no retrieval change can fix. faithfulness
1.00→0.89 is ~one claim on a tiny set — directionally real (more context → more room to over-reach),
but the magnitude is noisy. This is indicative, not definitive.

## In plain language
We tested handing the AI the **whole surrounding section** instead of just the single best-matching
paragraph. Result: the answers got **more complete and correct** (it had the fuller picture) — but
also **slightly less trustworthy** (with more text in front of it, the model occasionally said
something that *sounded* right but wasn't strictly backed by the source; grounding slipped from
perfect to ~one claim drifting). Like giving a student the whole chapter instead of one paragraph:
richer answers, but they start "filling in" from memory. Because this system's core promise is "every
claim is backed by a real citation", we won't trade that away — so the feature stays **built but off**
until we can get the richer answers *without* the trust drop.

## Next
1. ~~Tune the parent window down~~ — **tried (700), rejected**: it didn't recover faithfulness.
   Parent-size is not the lever.
2. **De-noise before any verdict-level decision:** larger, **human-reviewed** NTRS gold + `--runs N`.
   At n=5 the faithfulness numbers (1.00 / 0.89 / 0.825) are each ~one claim — too coarse to trust
   the *magnitude*; only the *direction* (ON costs grounding) is solid.
3. Keep `auto_merge` **opt-in** (default off). Reasonable **per-use-case** policy: enable it where
   completeness matters more than strict grounding, keep it off for safety-critical answers.
4. If grounding-under-more-context is the real problem, the lever is **not** a smaller parent but a
   better *generation* contract (prompt the model to cite only within the hit child's span) or
   **Stage-2 smaller children** (gated on Qdrant, ADR 0027) — both separate experiments.
