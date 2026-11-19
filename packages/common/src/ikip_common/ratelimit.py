"""Per-tenant rate limiting — a token bucket keyed by tenant (ADR 0036 / prod-readiness #144).

`RATE_LIMIT_PER_MINUTE` existed but was only ever a *global* number — nothing enforced it **per
tenant**, so one tenant could consume all the capacity and starve the others. That breaks the
multi-tenant isolation promise (NFR10) at the *resource* level, not just the data level. This port
enforces it: each tenant gets its own token bucket; a request that can't take a token is refused
(HTTP 429 + Retry-After at the edge).

Local-first (ADR 0003): the default `InMemoryRateLimiter` is correct for a single process and for
tests (`clock` injectable → no sleeping); a shared, distributed limiter (Redis) is the drop-in
multi-instance swap behind the same port. **Disabled by default** (`RATE_LIMIT_ENABLED=false`) so
nothing throttles until it's turned on — same opt-in discipline as the budget cap (ADR 0034).
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from functools import lru_cache
from typing import Protocol, runtime_checkable


@runtime_checkable
class RateLimiter(Protocol):
    """Per-tenant limiter. `allow` takes a token if one is available (and returns True); otherwise
    returns False. `retry_after` is the seconds until the next token — for the 429 Retry-After."""

    def allow(self, tenant_id: uuid.UUID) -> bool: ...
    def retry_after(self, tenant_id: uuid.UUID) -> float: ...


class NullRateLimiter:
    """No limiting — always allows. The default when rate limiting is disabled."""

    def allow(self, tenant_id: uuid.UUID) -> bool:  # noqa: ARG002
        return True

    def retry_after(self, tenant_id: uuid.UUID) -> float:  # noqa: ARG002
        return 0.0


class InMemoryRateLimiter:
    """Per-tenant **token bucket**: the bucket holds up to `rate_per_minute` tokens (one minute's
    worth, so a burst is allowed) and refills continuously at `rate_per_minute / 60` tokens/sec. One
    token per request. Thread-safe; `clock` injectable for tests. Single-process (local-first); a
    Redis-backed limiter is the multi-instance swap behind the `RateLimiter` port (ADR 0036)."""

    def __init__(
        self, rate_per_minute: int, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._rate = float(rate_per_minute)
        self._capacity = float(rate_per_minute)
        self._clock = clock
        self._buckets: dict[uuid.UUID, tuple[float, float]] = {}  # tenant -> (tokens, last_ts)
        self._lock = threading.Lock()

    def _refill(self, tenant_id: uuid.UUID) -> tuple[float, float]:
        # Caller holds the lock. Returns the current (tokens, now) after accruing elapsed tokens.
        now = self._clock()
        tokens, last = self._buckets.get(tenant_id, (self._capacity, now))
        tokens = min(self._capacity, tokens + (now - last) * self._rate / 60.0)
        return tokens, now

    def allow(self, tenant_id: uuid.UUID) -> bool:
        with self._lock:
            tokens, now = self._refill(tenant_id)
            if tokens >= 1.0:
                self._buckets[tenant_id] = (tokens - 1.0, now)
                return True
            self._buckets[tenant_id] = (tokens, now)
            return False

    def retry_after(self, tenant_id: uuid.UUID) -> float:
        with self._lock:
            tokens, _ = self._refill(tenant_id)
            if tokens >= 1.0:
                return 0.0
            return (1.0 - tokens) * 60.0 / self._rate  # seconds to accrue the next whole token


def build_rate_limiter(
    rate_per_minute: int | None = None, *, enabled: bool | None = None
) -> RateLimiter:
    """Factory: an `InMemoryRateLimiter` when enabled, else a `NullRateLimiter` (disabled). Reads
    `RATE_LIMIT_ENABLED` + `RATE_LIMIT_PER_MINUTE` from Settings unless overridden. Mirrors
    `build_budget_ledger` — the app builds one at startup; tests construct the impl directly."""
    if enabled is None or rate_per_minute is None:
        from ikip_common.config import get_settings

        settings = get_settings()
        if enabled is None:
            enabled = getattr(settings, "rate_limit_enabled", False)
        if rate_per_minute is None:
            rate_per_minute = getattr(settings, "rate_limit_per_minute", 120)
    return InMemoryRateLimiter(rate_per_minute or 120) if enabled else NullRateLimiter()


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    """Process-wide singleton — buckets must persist ACROSS requests (unlike per-request deps). A
    shared Redis limiter is the multi-instance swap (ADR 0036). `cache_clear()` resets it."""
    return build_rate_limiter()
