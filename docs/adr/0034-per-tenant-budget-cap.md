# 0034. Per-tenant spend cap (BudgetLedger port) — a hard budget ceiling

- **Status:** Accepted — in-memory ledger + `/ask` enforcement now; persistent backend deferred.
- **Date:** 2026-11-19
- **Deciders:** Architect, PM
- **Related:** [ADR 0003](./0003-local-first-ports-and-adapters.md) (ports, local-first) · [ADR 0013](./0013-llmops-observability-otel-langfuse.md) (cost metrics — *observe*) · [ADR 0033](./0033-agentic-foundation-and-query-decomposition.md) (agentic loop — the spend *amplifier*) · [PRODUCTION-READINESS.md](../PRODUCTION-READINESS.md) #146

## Context
Token accounting exists (`telemetry/metrics.record_cost`) but it only **observes** — nothing *stops*
paid work when a tenant runs away. The agentic loop (ADR 0033) makes this sharper: it spends **N LLM
calls per query**, not one, so a buggy policy or a hostile tenant can burn budget fast. There was no
hard ceiling: the only cap was the agent loop's `AgentBudget.max_cost_usd`, which **defaulted to 0.0
(off)**. This is prod-readiness blocker #146.

## Decision
A **`BudgetLedger` port** (`ikip_common/budget.py`) is the enforcement seam: `would_exceed(tenant,
cost)` guards *before* a paid op, `charge(tenant, cost)` records *after*, `spent`/`remaining` report.

1. **Local-first impls (ADR 0003).** `InMemoryBudgetLedger` (thread-safe dict + one shared cap) is
   the default and the test impl; `NullBudgetLedger` (never blocks) is selected when no cap is set.
   `build_budget_ledger()` reads `IKIP_BUDGET_CAP_USD` (**0 = disabled**, so nothing changes until a
   cap is configured — same opt-in discipline as every knob). `get_budget_ledger()` is the
   process-wide singleton (spend must accumulate *across* requests).
2. **Enforce at `/ask` now.** The handler refuses with **HTTP 429** when `remaining(tenant) <= 0`
   *before* retrieval/generation, and `charge`s the **same estimated cost** it already computes for
   metrics (`estimate_cost_usd`) *after*. One estimate, two sinks (metrics + ledger).
3. **Cap the agentic loop by default.** `AgentBudget.max_cost_usd` now defaults to a non-zero value,
   and `make_agentic_retrieve` passes a real per-step `cost_fn` + (when given a `ledger` + tenant)
   **degrades to abstention** if the query's worst-case cost would cross the cap — never overspends,
   never crashes. `max_steps` remains the primary per-query bound; this is the second one.

## Consequences
**Positive** — a tenant can no longer run away on cost; the agentic amplifier is bounded per-query
*and* per-tenant; the ledger is a clean port the whole system can call; disabled-by-default means zero
behaviour change until a cap is set.

**Negative / limits (deferred, measure-first):**
- **In-memory ledger is per-process** — correct for a single instance; a **multi-instance** deploy
  needs a shared persistent ledger (Redis/Postgres) + **reset windows** (daily/monthly) + per-tenant
  configurable caps. That is the drop-in prod swap behind this same port, deferred until a
  multi-instance deployment exists.
- **Estimated cost, not metered** — uses the indicative `estimate_cost_usd` (chars/4 × rates), not
  provider usage counters. A hard ceiling wants a conservative estimate, which this is; exact metering
  is a follow-up.
- **No pre-emption mid-request** — the cap is checked per request, not mid-generation; a single
  request can slightly overshoot (bounded by one request's cost).
- **Alert-before-stop** (warn at e.g. 80%) is not wired yet — the current behaviour is a hard 429 at
  100%. Alerting is the next slice.

## Alternatives rejected
- **A global-only cap** — doesn't isolate tenants (one tenant could still starve the global budget).
- **Enforce only in the agent loop** — misses the live `/ask` generation path (the majority of spend
  today, since the agentic controller isn't wired into `/ask` yet).
- **Persistent ledger now** — premature: single-instance today; local-first says build the port + the
  in-memory impl, swap the backend when a measured need (multi-instance) appears.
