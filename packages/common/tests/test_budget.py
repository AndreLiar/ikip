"""Per-tenant spend cap tests (ADR 0034 / prod-readiness #146). Pure — no DB/LLM."""

import uuid

from ikip_common.budget import (
    BudgetLedger,
    InMemoryBudgetLedger,
    NullBudgetLedger,
    build_budget_ledger,
    get_budget_ledger,
)

T1 = uuid.UUID("c0f90000-0000-4000-8000-000000000001")
T2 = uuid.UUID("c0f90000-0000-4000-8000-000000000002")


def test_in_memory_accumulates_and_reports_per_tenant() -> None:
    led = InMemoryBudgetLedger(cap_usd=1.0)
    led.charge(T1, 0.3)
    led.charge(T1, 0.2)
    led.charge(T2, 0.9)
    assert led.spent(T1) == 0.5
    assert round(led.remaining(T1), 4) == 0.5
    assert led.spent(T2) == 0.9  # tenants are isolated
    assert round(led.remaining(T2), 4) == 0.1


def test_would_exceed_guards_on_the_cap() -> None:
    led = InMemoryBudgetLedger(cap_usd=1.0)
    led.charge(T1, 0.9)
    assert led.would_exceed(T1, 0.2) is True  # 0.9 + 0.2 > 1.0
    assert led.would_exceed(T1, 0.1) is False  # 0.9 + 0.1 == 1.0, not over
    assert led.would_exceed(T2, 0.2) is False  # other tenant untouched


def test_remaining_never_negative() -> None:
    led = InMemoryBudgetLedger(cap_usd=0.5)
    led.charge(T1, 0.8)  # overshoot (one request can exceed; cap bites next turn)
    assert led.remaining(T1) == 0.0
    assert led.would_exceed(T1, 0.01) is True


def test_null_ledger_never_blocks() -> None:
    led = NullBudgetLedger()
    led.charge(T1, 1_000_000.0)
    assert led.would_exceed(T1, 1_000_000.0) is False
    assert led.remaining(T1) == float("inf")
    assert led.spent(T1) == 0.0


def test_factory_disabled_when_cap_not_positive() -> None:
    assert isinstance(build_budget_ledger(0.0), NullBudgetLedger)
    assert isinstance(build_budget_ledger(-1.0), NullBudgetLedger)
    assert isinstance(build_budget_ledger(5.0), InMemoryBudgetLedger)


def test_build_satisfies_the_port() -> None:
    assert isinstance(build_budget_ledger(1.0), BudgetLedger)
    assert isinstance(build_budget_ledger(0.0), BudgetLedger)


def test_get_budget_ledger_is_a_singleton() -> None:
    get_budget_ledger.cache_clear()
    a = get_budget_ledger()
    b = get_budget_ledger()
    assert a is b  # spend must accumulate across requests → same instance
    get_budget_ledger.cache_clear()
