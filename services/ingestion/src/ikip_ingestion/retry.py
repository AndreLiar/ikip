"""Retry + dead-letter policy for ingestion jobs (Story 2.6 AC3). Pure/testable.

A job that fails is retried up to `max_attempts` with exponential backoff; once
attempts are exhausted it goes to the dead-letter state. This policy is
side-effect-free (it computes *what* should happen); the Dagster step applies it
to the `ingestion_job` via the repository and the `JobQueue` port.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RetryDecision(StrEnum):
    retry = "retry"  # re-run after backoff
    dead_letter = "dead_letter"  # give up -> DLQ


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_s: float = 2.0
    max_delay_s: float = 300.0

    def should_retry(self, attempts: int) -> RetryDecision:
        """Given the number of attempts already made, decide retry vs dead-letter."""
        return RetryDecision.retry if attempts < self.max_attempts else RetryDecision.dead_letter

    def backoff_delay_s(self, attempts: int) -> float:
        """Exponential backoff for the next attempt (capped)."""
        delay = self.base_delay_s * (2 ** max(0, attempts - 1))
        return min(delay, self.max_delay_s)
