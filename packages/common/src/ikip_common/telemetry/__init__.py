"""Telemetry: port + adapters (Story 5.4, ADR 0013).

Port `Telemetry`/`Span`; adapters `LangfuseTelemetry` (lazy SDK) + `FakeTelemetry` (CI).
`NullTelemetry` is a no-op used when Langfuse isn't configured, so tracing is always a
safe call. `build_telemetry` returns Langfuse when configured, else the no-op.
"""

from __future__ import annotations

from types import TracebackType

from ikip_common.config import Settings, get_settings
from ikip_common.telemetry.base import Span, SpanContext, Telemetry
from ikip_common.telemetry.fake import FakeSpan, FakeTelemetry


class _NullSpan:
    trace_id = ""

    def set_metadata(self, **fields: object) -> None: ...
    def set_cost(self, *, cost_usd: float | None = None, tokens: int | None = None) -> None: ...
    def finish(self, *, status: str = "ok") -> None: ...
    def __enter__(self) -> _NullSpan:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return False


class NullTelemetry:
    """No-op Telemetry; tracing calls are safe even when no backend is configured."""

    def span(self, name: str, **metadata: object) -> _NullSpan:
        return _NullSpan()


def build_telemetry(settings: Settings | None = None) -> Telemetry:
    """Langfuse telemetry when credentials are present, else a no-op (no hard dependency
    on an observability backend being configured)."""
    s = settings or get_settings()
    if s.langfuse_public_key is not None and s.langfuse_secret_key is not None:
        try:
            from ikip_common.telemetry.langfuse import LangfuseTelemetry

            # Construct eagerly: the SDK is imported in __init__, so a missing optional
            # dependency surfaces here as ImportError and we can degrade cleanly.
            return LangfuseTelemetry(s)
        except ImportError:
            # Credentials set but the optional `telemetry` dep group isn't installed
            # (dev/CI without langfuse). Degrade to a no-op rather than crash /ask.
            import logging

            logging.getLogger("ikip_common").warning(
                "langfuse credentials set but 'langfuse' is not installed; "
                "install the 'telemetry' group to enable tracing. Falling back to no-op."
            )
            return NullTelemetry()
    return NullTelemetry()


__all__ = [
    "Telemetry",
    "Span",
    "SpanContext",
    "FakeTelemetry",
    "FakeSpan",
    "NullTelemetry",
    "build_telemetry",
]
