# Runbook — Prompt evaluation workflow

How to evaluate a prompt (or model-config) change in IKIP and ship it safely. A prompt is a
**versioned artifact**, evaluated against **gold datasets** with **layered metrics**, then
**promoted behind gates**. This ties together Stories 5.1–5.6 and ADRs [0013](../adr/0013-llmops-observability-otel-langfuse.md) / [0016](../adr/0016-rag-evaluation-custom-plus-ragas.md).

**Golden rule:** never edit a prompt in place. A change = a **new version** (`v2`, `v3`, …).
`v1` stays immutable so rollback is always a pointer flip.

---

## 0. Prerequisites (once)
- Azure OpenAI + a DB are configured (`.env`) for the live commands.
- A seeded eval tenant exists and a resolved gold file points at real chunks:
  ```bash
  uv run --group embeddings python -m ikip_common.eval seed \
      --tenant <uuid> --out eval-results/failure_modes.resolved.json
  ```
- (Optional) OTLP configured so eval metrics land on the Grafana eval dashboard
  (see `grafana-cloud-observability.md`).

The eval CLI: `run · check · promote · safety · config · seed · ragas · compare · gold-status · calibrate · multiturn`.

---

## 1. Create the new version
Prompts/configs live in `packages/common/src/ikip_common/llm/prompt_config/<version>.json`.
Derive the new version from the shipped one (keep everything except what you're changing):

```python
from dataclasses import replace
from ikip_common.llm.prompts import BUILTIN_V1, default_registry
v2 = replace(BUILTIN_V1, version="v2", generate_system=BUILTIN_V1.generate_system + "\n- <your new rule>")
default_registry().write(v2)        # writes v2.json (immutable); does NOT activate it
```
Check it registered: `uv run python -m ikip_common.eval config list` (marks the active one).

---

## 2. Evaluate offline — three layers (cheap → expensive)

| Layer | Command | Measures | Cadence |
|---|---|---|---|
| **Deterministic** (free, reproducible) | `eval run --gold <set> --tenant <uuid>` | `behavior_conformity`, `recall_at_k`, `citation_resolution`, `citation_grounding_coverage` | every push |
| **Safety** (blocking, 100%) | `eval safety` | abstention on unsafe / unsupported / poisoned content | every push |
| **Ragas** (LLM-judged, costs tokens) | `eval compare --sample N --runs M --budget-usd <cap>` | `faithfulness`, `answer_relevancy`, `answer_correctness` + custom-vs-Ragas divergence, cost, variance | nightly / on demand |

First **activate the candidate** so the harness exercises it, then run:
```bash
uv run python -m ikip_common.eval config activate --version v2
uv run --group embeddings python -m ikip_common.eval run \
    --gold eval-results/failure_modes.resolved.json --tenant <uuid> --out eval-results
uv run --group embeddings python -m ikip_common.eval safety
```
Deterministic metrics gate every push; Ragas is sampled + budget-capped (it is non-deterministic — see Gotchas).

> **Reliability, not a single run.** The chat model is a reasoning model at temperature 1 → non-deterministic. A prompt fix is a **probabilistic mitigation**: run the key case N times and report the abstention/conformity rate (e.g. 5–6/6), don't conclude on one run.

---

## 3. Compare to the approved baseline (regression)
```bash
uv run python -m ikip_common.eval check --out eval-results --tolerance 0.02
```
Exit 1 if any higher-is-better metric dropped more than the tolerance below `baseline.json`.
(Compare custom-vs-Ragas divergence from `comparison.json` to spot entailment gaps the
deterministic metrics can't see.)

---

## 4. Promote — only if the gates pass (the governance step)
```bash
uv run --group embeddings python -m ikip_common.eval config promote --version v2 --eval eval-results
```
Activates `v2` **only if** retrieval + groundedness + safety gates pass (else exits 1), then
syncs the prompt to Langfuse (`label=production`) if configured. This is the full loop:
**measure → version → gated promote → re-measure.**

CI reinforces it: any PR touching `prompt_config/**` triggers `config-regression.yml`
(registry integrity + groundedness/retrieval harness + the safety gate).

---

## 5. Observe in production
- Each `/ask` stamps `query_trace.model_version = "{deployment}+prompt:{version}"` and a
  Langfuse `trace_id` → you can attribute any quality shift to the exact prompt version.
- The Grafana **eval dashboard** trends `recall_at_k`, groundedness, conformity; **alerts**
  fire on regression (`grafana/alerts/rules.yaml`).
- Run the eval nightly (`ragas-eval.yml`) so the trend fills and regressions surface.

---

## 6. Rollback
```bash
uv run python -m ikip_common.eval config activate --version v1
```
Immutable versions → a rollback is instant and always safe.

---

## Worked example — the conflicting-sources fix (real, 2026-11-11)
1. **Found by the eval:** `eval compare` flagged 1 divergent case (coverage 1.0 vs Ragas
   faithfulness 0.0) + `eval run` showed `behavior_conformity = 0.875` — the assistant
   answered "10 bar" where two *current* sources said 8 bar and 10 bar (gold: abstain).
2. **New version:** `v2` adds "abstain + name the conflict when ≥2 current sources disagree".
3. **Re-measure:** `eval run` → `behavior_conformity` 0.875 → **1.0**; reliability 5–6/6 runs.
4. **Gated promote:** `config promote --version v2` → retrieval+groundedness+safety ok → active.
5. **After:** `eval compare` → **0 divergent**, agreement 1.0.

Artifacts: `docs/learning/missions/MISSION-029/evidence/comparison.{live,v2-after}.json`.

---

## Gotchas
- **Non-determinism** (reasoning model @ temp 1): measure reliability over N runs; a prompt
  hint is probabilistic, not a guarantee. The robust, deterministic version of a guard lives
  in code (e.g. a grounding-level contradiction check), not only in the prompt.
- **Trust the judge before trusting its scores:** calibrate the grounding/Ragas judge against
  human labels first — `eval calibrate --min-accuracy 0.8` (reports accuracy / Cohen's kappa).
  Optimizing against an un-calibrated judge optimizes against its bias.
- **Reference quality:** `faithfulness` needs no reference (judges answer-vs-context), so it's
  the safest headline metric; `answer_correctness`/`context_recall` depend on gold
  `ground_truth` — check provenance with `eval gold-status` (SME-reviewed vs not).
- **Language:** deterministic metrics are language-agnostic; Ragas is English-biased — use the
  FR gold (`failure_modes_fr.json`) + the `by_language` breakdown to keep that visible.

## See also
- [rag-evaluation-metrics](../learning/concepts/rag-evaluation-metrics.md) — how to read each number.
- [grafana-cloud-observability](grafana-cloud-observability.md) — the eval/ops dashboards.
- ADR [0016](../adr/0016-rag-evaluation-custom-plus-ragas.md) (custom + Ragas), [0013](../adr/0013-llmops-observability-otel-langfuse.md) (prompt management + tracing).
