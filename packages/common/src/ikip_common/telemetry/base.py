"""Telemetry port (Story 5.4, ADR 0013).

Abstracts LLM/RAG tracing behind a small interface so the domain never imports a
specific backend. The default adapter is Langfuse (OTel-backed, ADR 0013); a
`FakeTelemetry` records spans in-memory for CI with no network. A `Span` is the unit
of correlation: it carries a `trace_id` (persisted on `query_trace` to correlate the
durable record with the Langfuse trace), accepts structured metadata, and can record
cost/usage + a terminal status.

Data governance (Story 5.4 AC4): callers pass **IDs and metadata**, not raw prompts or
document text, unless content capture is explicitly enabled (Settings.telemetry_capture_content).
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, runtime_checkable


@runtime_checkable
class Span(Protocol):
    @property
    def trace_id(self) -> str:
        """Backend trace id used to correlate the durable query_trace row with the UI."""
        ...

    def set_metadata(self, **fields: object) -> None: ...

    def set_cost(self, *, cost_usd: float | None = None, tokens: int | None = None) -> None: ...

    def finish(self, *, status: str = "ok") -> None: ...


@runtime_checkable
class Telemetry(Protocol):
    def span(self, name: str, **metadata: object) -> SpanContext:
        """Open a span; use as a context manager: `with tel.span("ask", tenant=...) as s:`."""
        ...


class SpanContext(Protocol):
    """A context manager yielding a `Span`."""

    def __enter__(self) -> Span: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...
