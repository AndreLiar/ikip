"""Per-tenant spend ceiling — a hard budget cap (ADR 0034 / prod-readiness #146).

Token accounting already exists (`telemetry/metrics.record_cost`) but it only *observes* — nothing
*stops* paid work when a tenant runs away. This port is the enforcement seam: accumulate estimated
cost per tenant and **refuse new paid work once the cap is crossed**. It is deliberately
amplifier-aware — the agentic loop spends N LLM calls per query (ADR 0033), so a runaway agent is
the first thing this protects.

Local-first (ADR 0003): the default `InMemoryBudgetLedger` is correct for a single process and for
tests; a **persistent, shared** ledger (Redis/Postgres, with reset windows) is the drop-in prod
replacement behind the same port — deferred until a multi-instance deployment needs it (noted in
ADR 0034). Disabled by default (`cap_usd <= 0` → `NullBudgetLedger`), so nothing changes until a cap
is configured — same opt-in discipline as every other knob here.

Enforcement contract: callers ask `would_exceed(tenant, estimate)` **before** spending (degrade to
abstention if True — never crash, never overspend) and `charge(tenant, actual)` **after**. The
ledger never raises on the happy path; `BudgetExceededError` is available for callers that prefer
to fail loudly rather than degrade.
"""

from __future__ import annotations

import threading
import uuid
from functools import lru_cache
from typing import Protocol, runtime_checkable


class BudgetExceededError(Exception):
    """Raised by callers that choose to fail loudly when a tenant is over its cap."""


@runtime_checkable
class BudgetLedger(Protocol):
    """Per-tenant spend ceiling. `spent`/`remaining` report; `would_exceed` guards *before* a paid
    op; `charge` records *after* it. Implementations must be safe under concurrent requests."""

    def spent(self, tenant_id: uuid.UUID) -> float: ...
    def remaining(self, tenant_id: uuid.UUID) -> float: ...
    def would_exceed(self, tenant_id: uuid.UUID, cost_usd: float) -> bool: ...
    def charge(self, tenant_id: uuid.UUID, cost_usd: float) -> None: ...


class NullBudgetLedger:
    """No cap configured → never blocks, never accumulates. The default when `cap_usd <= 0`."""

    def spent(self, tenant_id: uuid.UUID) -> float:  # noqa: ARG002
        return 0.0

    def remaining(self, tenant_id: uuid.UUID) -> float:  # noqa: ARG002
        return float("inf")

    def would_exceed(self, tenant_id: uuid.UUID, cost_usd: float) -> bool:  # noqa: ARG002
        return False

    def charge(self, tenant_id: uuid.UUID, cost_usd: float) -> None:  # noqa: ARG002
        return None


class InMemoryBudgetLedger:
    """Dict-backed per-tenant ledger with one shared `cap_usd` (local-first / single process).
    Thread-safe (a lock guards the read-modify-write) so concurrent requests can't race the cap.
    A persistent, per-tenant-configurable, windowed ledger is the prod replacement (ADR 0034)."""

    def __init__(self, cap_usd: float) -> None:
        self._cap = cap_usd
        self._spent: dict[uuid.UUID, float] = {}
        self._lock = threading.Lock()

    def spent(self, tenant_id: uuid.UUID) -> float:
        with self._lock:
            return self._spent.get(tenant_id, 0.0)

    def remaining(self, tenant_id: uuid.UUID) -> float:
        with self._lock:
            return max(0.0, self._cap - self._spent.get(tenant_id, 0.0))

    def would_exceed(self, tenant_id: uuid.UUID, cost_usd: float) -> bool:
        with self._lock:
            return self._spent.get(tenant_id, 0.0) + cost_usd > self._cap

    def charge(self, tenant_id: uuid.UUID, cost_usd: float) -> None:
        with self._lock:
            self._spent[tenant_id] = self._spent.get(tenant_id, 0.0) + cost_usd


def build_budget_ledger(cap_usd: float | None = None) -> BudgetLedger:
    """Factory: an `InMemoryBudgetLedger` when a positive cap is set (arg or `IKIP_BUDGET_CAP_USD`),
    else a `NullBudgetLedger` (disabled). Mirrors `build_metrics`/`build_telemetry` — the app builds
    one at startup and passes it down; tests construct the impl directly."""
    if cap_usd is None:
        from ikip_common.config import get_settings

        cap_usd = getattr(get_settings(), "budget_cap_usd", 0.0)
    return InMemoryBudgetLedger(cap_usd) if cap_usd and cap_usd > 0 else NullBudgetLedger()


@lru_cache(maxsize=1)
def get_budget_ledger() -> BudgetLedger:
    """Process-wide singleton (spend must accumulate ACROSS requests, unlike the per-request deps).
    In-memory → correct for a single process; a shared persistent ledger is the multi-instance prod
    swap behind the same port (ADR 0034). `cache_clear()` resets it in tests."""
    return build_budget_ledger()
