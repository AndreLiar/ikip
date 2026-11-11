"""Telemetry port + adapter selection (Story 5.4). Pure: no DB, no Langfuse SDK."""

from __future__ import annotations

import pytest
from ikip_common.config import Settings
from ikip_common.telemetry import (
    FakeTelemetry,
    NullTelemetry,
    build_telemetry,
)


def _settings(**over) -> Settings:
    base = {
        "DATABASE_URL": "postgresql://u:p@host/db",
        "R2_ACCOUNT_ID": "a",
        "R2_ENDPOINT": "https://a.r2.cloudflarestorage.com",
        "R2_BUCKET": "b",
        "R2_ACCESS_KEY_ID": "ak",
        "R2_SECRET_ACCESS_KEY": "sk",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_SECRET": "x" * 36,
        # Isolate from any ambient .env langfuse creds so the no-cred path is exercised.
        "LANGFUSE_PUBLIC_KEY": None,
        "LANGFUSE_SECRET_KEY": None,
    }
    base.update(over)
    return Settings(**base)


def test_fake_span_records_name_metadata_cost() -> None:
    t = FakeTelemetry()
    with t.span("assistant.ask", tenant_id="t1", operation="ask") as span:
        span.set_metadata(status="answered")
        span.set_cost(cost_usd=0.0012, tokens=42)
    assert len(t.spans) == 1
    s = t.spans[0]
    assert s.name == "assistant.ask"
    assert s.metadata["operation"] == "ask"
    assert s.metadata["status"] == "answered"
    assert s.cost_usd == 0.0012 and s.tokens == 42
    assert s.status == "ok"
    assert s.trace_id  # stable id for correlation


def test_fake_span_marks_error_and_never_suppresses() -> None:
    t = FakeTelemetry()
    with pytest.raises(ValueError):
        with t.span("assistant.ask") as span:
            raise ValueError("boom")
    assert span.status == "error"  # exception propagated AND recorded


def test_null_telemetry_is_safe_noop() -> None:
    t = NullTelemetry()
    with t.span("x", k="v") as span:
        span.set_metadata(a=1)
        span.set_cost(cost_usd=1.0)
        span.finish(status="ok")
    assert span.trace_id == ""  # nothing to correlate when unconfigured


def test_build_telemetry_null_without_credentials() -> None:
    assert isinstance(build_telemetry(_settings()), NullTelemetry)


def test_build_telemetry_falls_back_when_langfuse_missing() -> None:
    # Credentials present but the optional SDK isn't installed in this env: /ask must
    # not crash — we degrade to a no-op rather than raise (AC: tracing is best-effort).
    try:
        import langfuse  # noqa: F401
    except ImportError:
        s = _settings(LANGFUSE_PUBLIC_KEY="pk", LANGFUSE_SECRET_KEY="sk")
        assert isinstance(build_telemetry(s), NullTelemetry)
    else:  # SDK present: builder returns the real adapter
        from ikip_common.telemetry.langfuse import LangfuseTelemetry

        s = _settings(LANGFUSE_PUBLIC_KEY="pk", LANGFUSE_SECRET_KEY="sk")
        assert isinstance(build_telemetry(s), LangfuseTelemetry)
