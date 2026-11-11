# MISSION-028 — Prompt/Model Config Versioning & Regression Gates (Epic 5, Story 5.5)

**Mode:** Guidé (architecture decision — source-of-truth for prompts — put to the user) then Autonome.
**Objective:** versioned prompt/model configs, gated by regression tests: a config change triggers the regression suite, promotion requires passing retrieval + groundedness + safety gates, and rollback is supported.
**Maps to:** Epic 5 / Story 5.5. Builds on the grounded-answer flow (3.5), the eval harness (3.6), the safety gate (5.3) and tracing (5.4).

## Decision — where prompts live (asked the user; chose Hybrid)
AC1 allows Langfuse prompt management **and/or** repo artifacts. The user chose **git as the source of truth + Langfuse as the runtime/UI mirror** (recorded in [ADR 0013](../../adr/0013-llmops-observability-otel-langfuse.md), 2026-11-11 update). Rationale: the governance ACs (2 = change triggers regression, 3 = gated promotion) map to a **PR diff + CI**, which a Langfuse-UI edit cannot provide; Langfuse stays swappable behind a port.

## What was built
- **Versioned registry** `llm/prompt_config/<version>.json` + `active.json`; `llm/prompts.py`:
  - `PromptConfig` (generate_system, judge_system, not_certified_notice, `ModelConfig`) + `content_hash` (version-independent, content-sensitive).
  - `BUILTIN_V1` is the canonical source of the shipped prompts; `v1.json` is generated from it and a test asserts `get("v1") == BUILTIN_V1` (no silent drift).
  - `PromptRegistry`: `versions/get/active/write/activate/promote`. `activate` = rollback (AC4, immutable artifacts). `promote` activates **only if gates pass** then syncs via a `PromptPublisher`.
  - `active_prompt_config()` (lru-cached) with a **built-in fallback** so config IO never breaks generation.
  - Gates: `evaluate_gates(eval_aggregate, safety_passed)` → `GateResult(retrieval, groundedness, safety)` with explicit floors (`DEFAULT_GATE_THRESHOLDS`); missing eval evidence fails by default.
  - `PromptPublisher` port + `LangfusePromptPublisher` (lazy SDK, publishes each prompt under label `production` with version+model config) + `NullPromptPublisher`; `build_prompt_publisher` degrades to no-op without SDK/creds.
- **Runtime wiring**: `build_answer_graph(..., prompts=None)` + `grounded_answer(..., prompts=None)` read the active config (generate_system + not-certified notice); `LLMGroundingValidator(chat_client, system=None)` reads the active judge prompt. v1 == current constants → zero behavior change (all prior tests green).
- **CLI** `python -m ikip_common.eval config {list,show,activate,promote}` — `activate` rolls back; `promote --version v2 --eval eval-results` runs the gates (retrieval+groundedness from `latest.json`, safety from the 5.3 suite) and only then activates + syncs; exit 1 when blocked.
- **CI** `.github/workflows/config-regression.yml` — path-filtered on the prompt config + consuming code; runs registry integrity + groundedness/retrieval harness + the safety gate (deterministic, no secrets). Full live metric regression stays the `eval run`/`check` CLI (manual/nightly).

## Acceptance (Story 5.5)
1. Prompts/model configs are versioned artifacts. — **[verified]** (`prompt_config/*.json` + `active.json`; Langfuse sync on promote; drift-guard test).
2. Changing a config triggers the regression suite. — **[verified]** (`config-regression.yml` path filter; deterministic suite).
3. Promotion requires passing retrieval + groundedness + safety gates. — **[verified]** (`evaluate_gates` + `PromptRegistry.promote`; CLI blocks with exit 1; tests for pass/block).
4. Rollback to a prior config version is supported. — **[verified]** (`activate` a prior immutable version; round-trip test; CLI `config activate`).

## Verification
- `config list` → `v1 (active)`; `config promote` **blocked** without eval evidence (retrieval/groundedness FAIL), **passes** with a good aggregate (exit 0), syncs to backend (no-op without SDK).
- ruff + format ✓; `pytest apps packages services` → 209 passed / 43 skipped; targeted embeddings suite (answer graph, grounding, safety, registry, wiring, harness) → 28 passed.

## Deliverables
- `llm/prompts.py`; `llm/prompt_config/{v1.json,active.json}`; wiring in `llm/answer.py` + `llm/grounding.py`.
- `eval/__main__.py` (`config` subcommands); `.github/workflows/config-regression.yml`.
- `tests/test_prompt_registry.py` (pure), `tests/test_prompt_config_wiring.py` (langgraph).
- ADR 0013 update.

## Follow-ups (noted)
- Wire `ModelConfig` (deployment/effort/temperature) into `build_chat_client` so model params are activated too (today versioned + synced + recorded, Settings is still the live deployment source).
- Record the active prompt config version on `query_trace.model_version` (5.4) for full change↔trace attribution.
- Nightly live `eval run` + `check` to produce the `latest.json` aggregate that `config promote` gates on.

## Concepts
Extends [grounded-answers](../../concepts/grounded-answers.md); realises [ADR 0013](../../adr/0013-llmops-observability-otel-langfuse.md) prompt-management decision. Related: [[MISSION-026]] (tracing), [[MISSION-027]] (safety gate).
