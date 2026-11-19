# 0035. Circuit breaker on the Azure OpenAI path — fail fast on a sustained outage

- **Status:** Accepted — breaker wraps the chat + embedding adapters now.
- **Date:** 2026-11-19
- **Deciders:** Architect
- **Related:** [ADR 0007/0020/0021](./0021-framework-boundary-langchain-langgraph-vs-data-plane.md) (Azure adapters behind ports) · [ADR 0034](./0034-per-tenant-budget-cap.md) (the other reliability primitive) · [PRODUCTION-READINESS.md](../PRODUCTION-READINESS.md) #145

## Context
The Azure OpenAI adapters (`llm/azure.py` embeddings, `llm/chat_azure.py` chat) retry 429s with
exponential backoff. That is correct for a **transient** blip but wrong for a **sustained** outage or
quota throttle: every request then pays the full backoff ladder before failing, so latency piles up
across all in-flight requests and the failure cascades. There was no fast-fail path (#145).

## Decision
A reusable **`CircuitBreaker`** (`ikip_common/resilience.py`) wraps the Azure calls:
- **closed** → calls flow, consecutive failures counted; at `failure_threshold` it **opens**.
- **open** → every call *fast-fails* with `CircuitOpenError` (Azure is **not** called) for
  `reset_timeout_s` — the caller can degrade (cache/abstain) instead of hanging.
- **half-open** → after the cooldown, one probe is allowed; success **closes** + resets, failure
  re-**opens**.
- Thread-safe (one shared breaker per adapter); `clock` is injectable so tests never sleep;
  `on_state_change` is a hook for metrics/logging (state transitions are logged at WARNING now).

Wired behind the existing ports, so the domain is untouched and fake-client tests need no network.
The breaker sits **outside** the retry loop: retries still absorb a transient 429 (that's a success);
only a batch/call that **exhausts** its retries counts as a breaker failure.

## Consequences
**Positive** — under a real outage the system fails fast and predictably instead of degrading into
timeouts; pairs with the budget cap (ADR 0034) as the two runtime-reliability primitives; the breaker
is reusable for any flaky dependency.

**Negative / limits (deferred):**
- **Per-process, per-adapter breaker** — not shared across instances or between chat/embeddings; a
  shared/coordinated breaker is a later refinement (same spirit as ADR 0034's in-memory ledger).
- **Multiple probes in half-open** — concurrent calls can each probe; acceptable for a first cut
  (the threshold still bounds damage), tighten with a single-probe gate if it matters.
- **Metric emission is via the `on_state_change` hook + WARNING logs** today; wiring the hook to the
  `Metrics` port (a breaker-state gauge on the Grafana dashboard) is a thin follow-up.
- Thresholds (`failure_threshold=5`, `reset_timeout_s=30`) are sensible defaults, not yet tuned
  against production 429 patterns.

## Alternatives rejected
- **Keep retry-only** — the status quo; cascades under sustained throttle (#145).
- **A third-party breaker lib** — unnecessary dependency for ~70 lines; local-first prefers a small,
  owned, fully-tested primitive (same call as building our own RRF / cache).
