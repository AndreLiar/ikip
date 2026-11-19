"""Circuit breaker tests (ADR 0035 / #145). Pure — a fake clock, no sleeping, no network."""

import pytest
from ikip_common.resilience import CircuitBreaker, CircuitOpenError, CircuitState


class _Clock:
    """Hand-advanced monotonic clock so tests control the cooldown without sleeping."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _boom() -> None:
    raise RuntimeError("dependency down")


def test_opens_after_threshold_consecutive_failures() -> None:
    cb = CircuitBreaker(failure_threshold=3, clock=_Clock())
    for _ in range(3):
        with pytest.raises(RuntimeError):
            cb.call(_boom)
    assert cb.state is CircuitState.OPEN


def test_open_fast_fails_without_calling_the_op() -> None:
    cb = CircuitBreaker(failure_threshold=2, reset_timeout_s=30, clock=_Clock())
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(_boom)
    calls = []
    with pytest.raises(CircuitOpenError):
        cb.call(lambda: calls.append(1))  # must NOT run while open
    assert calls == []


def test_success_resets_the_failure_count() -> None:
    cb = CircuitBreaker(failure_threshold=3, clock=_Clock())
    with pytest.raises(RuntimeError):
        cb.call(_boom)
    with pytest.raises(RuntimeError):
        cb.call(_boom)
    cb.call(lambda: "ok")  # a success before the threshold resets the counter
    with pytest.raises(RuntimeError):
        cb.call(_boom)
    assert cb.state is CircuitState.CLOSED  # 1 failure after the reset — not yet open


def test_half_opens_after_cooldown_then_closes_on_a_successful_probe() -> None:
    clock = _Clock()
    cb = CircuitBreaker(failure_threshold=1, reset_timeout_s=30, clock=clock)
    with pytest.raises(RuntimeError):
        cb.call(_boom)  # opens (threshold=1)
    assert cb.state is CircuitState.OPEN

    clock.t = 29.9  # still cooling down → fast-fail
    with pytest.raises(CircuitOpenError):
        cb.call(lambda: "ok")

    clock.t = 30.0  # cooldown elapsed → the next call probes (half-open) and succeeds → closes
    assert cb.call(lambda: "ok") == "ok"
    assert cb.state is CircuitState.CLOSED


def test_failed_probe_reopens_immediately() -> None:
    clock = _Clock()
    cb = CircuitBreaker(failure_threshold=1, reset_timeout_s=10, clock=clock)
    with pytest.raises(RuntimeError):
        cb.call(_boom)  # opens
    clock.t = 10.0  # cooldown elapsed → probe
    with pytest.raises(RuntimeError):
        cb.call(_boom)  # probe fails → re-open
    assert cb.state is CircuitState.OPEN


def test_on_state_change_hook_fires_on_transitions() -> None:
    seen: list[CircuitState] = []
    cb = CircuitBreaker(failure_threshold=1, clock=_Clock(), on_state_change=seen.append)
    with pytest.raises(RuntimeError):
        cb.call(_boom)  # closed -> open
    assert seen == [CircuitState.OPEN]
