"""Circuit breaker — fail fast instead of backing off on every call (ADR 0035 / #145).

The Azure OpenAI adapters retry 429s with exponential backoff. That is right for a *transient* blip
but wrong for a *sustained* outage/quota throttle: every request then pays the full backoff before
failing, so latency piles up and the failure cascades. A **circuit breaker** fixes that: after
`failure_threshold` consecutive failures it **opens** and *fast-fails* every call for
`reset_timeout_s` (raising `CircuitOpenError` without touching Azure), then **half-opens** for a
single probe — a success **closes** it, a failure re-**opens** it. The caller can then degrade
(serve cache / abstain) instead of hanging.

Pure + testable: `clock` is injectable so tests never sleep; `on_state_change` is a hook for
metrics/logging. Thread-safe — concurrent requests share one breaker and can't corrupt its state.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from enum import StrEnum
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    """Raised *instead of* calling the wrapped op while the breaker is OPEN (the fast-fail path)."""


class CircuitState(StrEnum):
    CLOSED = "closed"  # calls flow; failures are counted
    OPEN = "open"  # calls fast-fail; waiting out the cooldown
    HALF_OPEN = "half_open"  # one probe allowed to test recovery


class CircuitBreaker:
    """Fail-fast wrapper around a flaky dependency (the Azure OpenAI chat/embedding path, #145).

    Opens after `failure_threshold` consecutive failures; fast-fails for `reset_timeout_s`; then
    half-opens for a single probe (success → close + reset, failure → re-open). `clock` defaults to
    `time.monotonic` (injectable for tests); `on_state_change(state)` fires on every transition."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        reset_timeout_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        on_state_change: Callable[[CircuitState], None] | None = None,
        name: str = "circuit",
    ) -> None:
        self._threshold = failure_threshold
        self._reset = reset_timeout_s
        self._clock = clock
        self._on_change = on_state_change
        self._name = name
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def _transition(self, state: CircuitState) -> None:
        # Caller holds the lock. No-op when the state is unchanged (avoids spurious callbacks).
        if state is self._state:
            return
        self._state = state
        logger.warning("circuit '%s' -> %s", self._name, state.value)
        if self._on_change is not None:
            self._on_change(state)

    def call(self, fn: Callable[..., T], *args: object, **kwargs: object) -> T:
        """Run `fn` through the breaker. Raises `CircuitOpenError` (without calling `fn`) while open
        and cooling down; otherwise calls `fn`, records the outcome, and re-raises its errors."""
        with self._lock:
            if self._state is CircuitState.OPEN:
                if self._clock() - self._opened_at >= self._reset:
                    self._transition(CircuitState.HALF_OPEN)  # time to probe
                else:
                    raise CircuitOpenError(f"circuit '{self._name}' is open")

        try:
            result = fn(*args, **kwargs)
        except Exception:
            with self._lock:
                self._failures += 1
                # a failed probe (half-open) re-opens immediately; otherwise open at the threshold.
                if self._state is CircuitState.HALF_OPEN or self._failures >= self._threshold:
                    self._opened_at = self._clock()
                    self._transition(CircuitState.OPEN)
            raise
        with self._lock:
            self._failures = 0
            self._transition(CircuitState.CLOSED)  # a success closes (and resets) the breaker
        return result
