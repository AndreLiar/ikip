"""Langfuse adapter for the Telemetry port (Story 5.4, ADR 0013).

Lazy-imports the `langfuse` SDK (OTel-backed) so the core package stays light and CI
needs neither the SDK nor network. Credentials come from Settings (EU cloud or a
self-hosted host). A span maps to a Langfuse trace; metadata/cost/status update it.

Content governance (AC4): by default only IDs + metadata are attached. Raw prompts /
document content are attached ONLY when `Settings.telemetry_capture_content` is true.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

from ikip_common.config import Settings, get_settings


class TelemetryConfigError(RuntimeError):
    """Langfuse telemetry requested but credentials are missing."""


def _make_client(settings: Settings) -> Any:
    from langfuse import Langfuse

    if settings.langfuse_public_key is None or settings.langfuse_secret_key is None:
        raise TelemetryConfigError("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set")
    return Langfuse(
        public_key=settings.langfuse_public_key.get_secret_value(),
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        host=settings.langfuse_host,
    )


class _LangfuseSpan:
    def __init__(self, client: Any, name: str, metadata: dict) -> None:
        self._client = client
        # langfuse v5 API: `start_observation(as_type="span")` replaced v3's `start_span`. The loose
        # `>=3.0` pin had silently moved us to v5; the adapter was never run live, so it went
        # unnoticed — the pin is now `>=5,<6`. The span still exposes trace_id / update / end.
        self._span = client.start_observation(name=name, as_type="span", metadata=metadata)
        self.trace_id = self._span.trace_id

    def set_metadata(self, **fields: object) -> None:
        self._span.update(metadata=fields)

    def set_cost(self, *, cost_usd: float | None = None, tokens: int | None = None) -> None:
        self._span.update(
            usage_details={"total": tokens} if tokens is not None else None,
            cost_details={"total": cost_usd} if cost_usd is not None else None,
        )

    def finish(self, *, status: str = "ok") -> None:
        self._span.update(metadata={"status": status})
        self._span.end()

    def __enter__(self) -> _LangfuseSpan:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if exc_type is not None:
            self.finish(status="error")
        else:
            self.finish(status="ok")
        return False


class LangfuseTelemetry:
    def __init__(self, settings: Settings | None = None, client: Any = None) -> None:
        self._settings = settings or get_settings()
        self._client = client or _make_client(self._settings)

    def span(self, name: str, **metadata: object) -> _LangfuseSpan:
        return _LangfuseSpan(self._client, name, dict(metadata))
