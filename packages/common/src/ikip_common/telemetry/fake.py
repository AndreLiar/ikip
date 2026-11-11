"""In-memory Telemetry for tests (Story 5.4). Deterministic, no network.

Records spans so tests can assert what was traced (name, metadata, cost, status) and
read a stable `trace_id`. The span swallows nothing — exceptions propagate; the span is
marked `error` on the way out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import TracebackType


@dataclass
class FakeSpan:
    name: str
    trace_id: str
    metadata: dict = field(default_factory=dict)
    cost_usd: float | None = None
    tokens: int | None = None
    status: str = "ok"

    def set_metadata(self, **fields: object) -> None:
        self.metadata.update(fields)

    def set_cost(self, *, cost_usd: float | None = None, tokens: int | None = None) -> None:
        if cost_usd is not None:
            self.cost_usd = cost_usd
        if tokens is not None:
            self.tokens = tokens

    def finish(self, *, status: str = "ok") -> None:
        self.status = status

    def __enter__(self) -> FakeSpan:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if exc_type is not None and self.status == "ok":
            self.status = "error"
        return False  # never suppress


class FakeTelemetry:
    def __init__(self) -> None:
        self.spans: list[FakeSpan] = []
        self._n = 0

    def span(self, name: str, **metadata: object) -> FakeSpan:
        self._n += 1
        s = FakeSpan(name=name, trace_id=f"trace-{self._n}", metadata=dict(metadata))
        self.spans.append(s)
        return s
