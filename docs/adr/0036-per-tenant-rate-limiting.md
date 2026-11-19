# 0036. Per-tenant rate limiting (RateLimiter port) — a token bucket per tenant

- **Status:** Accepted — in-memory limiter + `/ask` enforcement now; distributed limiter deferred.
- **Date:** 2026-11-19
- **Deciders:** Architect
- **Related:** [ADR 0003](./0003-local-first-ports-and-adapters.md) (ports, local-first) · [ADR 0034](./0034-per-tenant-budget-cap.md) (sister resource-isolation primitive) · [PRODUCTION-READINESS.md](../PRODUCTION-READINESS.md) #144

## Context
`RATE_LIMIT_PER_MINUTE` existed but was only a *global* number — nothing enforced it **per tenant**.
So one tenant's burst could consume all the capacity and starve the others: the multi-tenant
isolation guarantee (NFR10) held at the *data* level but not the *resource* level. This is
prod-readiness blocker #144.

## Decision
A **`RateLimiter` port** (`ikip_common/ratelimit.py`): `allow(tenant) -> bool` takes a token if one
is available; `retry_after(tenant)` gives the seconds to the next token (for the 429 `Retry-After`).

1. **Token bucket, per tenant.** `InMemoryRateLimiter` keeps a bucket of up to `rate_per_minute`
   tokens (one minute's worth → a burst is allowed) refilling continuously at `rate/60` tokens/sec;
   one token per request. Thread-safe; `clock` injectable (tests don't sleep).
2. **Enforce at `/ask`, first.** The handler calls `allow(tenant)` *before* the budget check (it's
   the cheapest guard) and returns **429 + `Retry-After`** on refusal.
3. **Disabled by default** (`RATE_LIMIT_ENABLED=false`). `build_rate_limiter()` / `get_rate_limiter()`
   mirror the budget ledger (factory + process-wide singleton); the limiter is opt-in so nothing
   throttles until it's turned on.

## Consequences
**Positive** — a tenant can no longer starve the others on request volume; completes the
resource-isolation pair with the budget cap (ADR 0034); the bucket allows a reasonable burst then
smooths to the configured rate.

**Negative / limits (deferred):**
- **In-memory, per-process** — correct for a single instance; a **distributed limiter (Redis)** is the
  multi-instance swap behind the same port (several API pods must share the bucket, else the effective
  limit is N×). Deferred until multi-instance.
- **Requests/min only** — the richer "tokens/min" cap (large-context queries cost more) is a
  follow-up; requests/min is the first, highest-value cut.
- **Per-tenant uniform rate** — one `RATE_LIMIT_PER_MINUTE` for all tenants; per-tenant tiers are a
  config follow-up.
- **No throttle metric yet** — the 429 is observable via the request-metrics status; a dedicated
  throttle counter is a thin follow-up.

## Alternatives rejected
- **Global-only limit (status quo)** — doesn't isolate tenants (#144).
- **A reverse-proxy / gateway limit** — per-tenant keying needs app context (the authenticated
  principal); doing it in-app keeps the policy with the tenant model and is testable with fakes.
