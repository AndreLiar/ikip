"""Retry/dead-letter policy tests (Story 2.6 AC3). Pure."""

from ikip_ingestion.retry import RetryDecision, RetryPolicy


def test_retries_until_max_then_dead_letters() -> None:
    p = RetryPolicy(max_attempts=3)
    assert p.should_retry(0) is RetryDecision.retry
    assert p.should_retry(2) is RetryDecision.retry
    assert p.should_retry(3) is RetryDecision.dead_letter
    assert p.should_retry(4) is RetryDecision.dead_letter


def test_exponential_backoff_is_capped() -> None:
    p = RetryPolicy(base_delay_s=2.0, max_delay_s=10.0)
    assert p.backoff_delay_s(1) == 2.0
    assert p.backoff_delay_s(2) == 4.0
    assert p.backoff_delay_s(3) == 8.0
    assert p.backoff_delay_s(10) == 10.0  # capped
