"""Per-tenant rate limiter tests (ADR 0036 / #144). Pure — a fake clock, no sleeping, no network."""

import uuid

import pytest
from ikip_common.ratelimit import (
    InMemoryRateLimiter,
    NullRateLimiter,
    RateLimiter,
    build_rate_limiter,
    get_rate_limiter,
)

T1 = uuid.UUID("c0f90000-0000-4000-8000-000000000001")
T2 = uuid.UUID("c0f90000-0000-4000-8000-000000000002")


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_allows_a_full_minute_burst_then_throttles() -> None:
    clock = _Clock()
    rl = InMemoryRateLimiter(3, clock=clock)  # 3/min → bucket holds 3
    assert [rl.allow(T1) for _ in range(3)] == [True, True, True]
    assert rl.allow(T1) is False  # bucket drained


def test_refills_over_time() -> None:
    clock = _Clock()
    rl = InMemoryRateLimiter(60, clock=clock)  # 60/min → 1 token/sec
    for _ in range(60):
        rl.allow(T1)
    assert rl.allow(T1) is False
    clock.t = 1.0  # one second → one token back
    assert rl.allow(T1) is True
    assert rl.allow(T1) is False


def test_tenants_are_isolated() -> None:
    clock = _Clock()
    rl = InMemoryRateLimiter(1, clock=clock)
    assert rl.allow(T1) is True
    assert rl.allow(T1) is False  # T1 drained
    assert rl.allow(T2) is True  # T2 untouched


def test_retry_after_reports_seconds_to_next_token() -> None:
    clock = _Clock()
    rl = InMemoryRateLimiter(60, clock=clock)  # 1 token/sec
    rl.allow(T1)  # drains the single... no — 60 capacity; drain it
    for _ in range(59):
        rl.allow(T1)
    assert rl.allow(T1) is False
    assert rl.retry_after(T1) == pytest.approx(1.0, abs=0.01)  # ~1s to the next token
    assert rl.retry_after(T2) == 0.0  # a fresh tenant isn't waiting


def test_null_limiter_always_allows() -> None:
    rl = NullRateLimiter()
    assert all(rl.allow(T1) for _ in range(1000))
    assert rl.retry_after(T1) == 0.0


def test_factory_and_port() -> None:
    assert isinstance(build_rate_limiter(10, enabled=True), InMemoryRateLimiter)
    assert isinstance(build_rate_limiter(10, enabled=False), NullRateLimiter)
    assert isinstance(build_rate_limiter(10, enabled=True), RateLimiter)


def test_get_rate_limiter_is_a_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    import ikip_common.config as cfg

    monkeypatch.setattr(
        cfg,
        "get_settings",
        lambda: type("S", (), {"rate_limit_enabled": True, "rate_limit_per_minute": 5})(),
    )
    get_rate_limiter.cache_clear()
    assert get_rate_limiter() is get_rate_limiter()  # buckets persist across requests
    get_rate_limiter.cache_clear()
