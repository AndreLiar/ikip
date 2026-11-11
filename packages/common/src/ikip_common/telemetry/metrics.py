"""Infra metrics port + OTel adapter (Story 5.6, ADR 0013).

The `Telemetry` port (Story 5.4) carries LLM/RAG traces to Langfuse. This `Metrics` port
carries operational numbers — request latency, error rate, token cost, and eval-quality
gauges — to Grafana Cloud via OTLP (OpenTelemetry metrics). The adapter is lazy-imported;
`build_metrics` returns a no-op when no OTLP endpoint is configured, so the API runs
unchanged locally and tests inject `FakeMetrics`.

Metric names (Prometheus-exposed by Grafana Cloud; used by grafana/dashboards/*.json):
  ikip_request_duration_ms   Histogram  attrs: operation, status
  ikip_requests_total        Counter    attrs: operation, status
  ikip_request_cost_usd      Counter    (sum of estimated $ per answered request)
  ikip_eval_quality          Gauge      attrs: metric (recall_at_k_mean, groundedness, …)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Metrics(Protocol):
    def record_request(self, *, operation: str, latency_ms: float, status: str) -> None: ...
    def record_cost(self, *, cost_usd: float, tokens: int = 0) -> None: ...
    def set_eval_gauge(self, metric: str, value: float) -> None: ...
    def flush(self) -> None: ...


class NullMetrics:
    """No-op metrics; safe when no OTLP backend is configured."""

    def record_request(self, *, operation: str, latency_ms: float, status: str) -> None: ...
    def record_cost(self, *, cost_usd: float, tokens: int = 0) -> None: ...
    def set_eval_gauge(self, metric: str, value: float) -> None: ...
    def flush(self) -> None: ...


class FakeMetrics:
    """Records calls so tests can assert what was measured (no OTLP)."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.costs: list[dict] = []
        self.gauges: dict[str, float] = {}

    def record_request(self, *, operation: str, latency_ms: float, status: str) -> None:
        self.requests.append({"operation": operation, "latency_ms": latency_ms, "status": status})

    def record_cost(self, *, cost_usd: float, tokens: int = 0) -> None:
        self.costs.append({"cost_usd": cost_usd, "tokens": tokens})

    def set_eval_gauge(self, metric: str, value: float) -> None:
        self.gauges[metric] = value

    def flush(self) -> None: ...


class OTelMetrics:
    """OpenTelemetry metrics exported via OTLP (Grafana Cloud). Lazy SDK import.

    Auth + endpoint come from the standard OTEL_EXPORTER_OTLP_* environment variables, read
    by the OTLP exporter directly. [untested live] — exercised with FakeMetrics; a real
    export needs the `otel` dependency group + a Grafana Cloud OTLP endpoint.
    """

    def __init__(self, settings=None) -> None:  # noqa: ANN001
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource

        from ikip_common.config import get_settings

        s = settings or get_settings()
        reader = PeriodicExportingMetricReader(OTLPMetricExporter())
        self._provider = MeterProvider(
            resource=Resource.create({"service.name": s.otel_service_name}),
            metric_readers=[reader],
        )
        meter = self._provider.get_meter("ikip")
        self._latency = meter.create_histogram("ikip_request_duration_ms", unit="ms")
        self._requests = meter.create_counter("ikip_requests_total")
        self._cost = meter.create_counter("ikip_request_cost_usd")
        self._eval: dict[str, float] = {}
        self._eval_gauge = meter.create_observable_gauge(
            "ikip_eval_quality",
            callbacks=[lambda _opts: self._observe_eval()],
        )

    def _observe_eval(self):  # noqa: ANN202
        from opentelemetry.metrics import Observation

        return [Observation(v, {"metric": k}) for k, v in self._eval.items()]

    def record_request(self, *, operation: str, latency_ms: float, status: str) -> None:
        attrs = {"operation": operation, "status": status}
        self._latency.record(latency_ms, attrs)
        self._requests.add(1, attrs)

    def record_cost(self, *, cost_usd: float, tokens: int = 0) -> None:
        self._cost.add(cost_usd)

    def set_eval_gauge(self, metric: str, value: float) -> None:
        self._eval[metric] = value

    def flush(self) -> None:
        # Force an export now — essential for one-shot CLIs (eval run) that exit before the
        # periodic reader fires.
        self._provider.force_flush()


def build_metrics(settings=None) -> Metrics:  # noqa: ANN001
    """OTel metrics when an OTLP endpoint is configured + the SDK is installed, else no-op."""
    from ikip_common.config import get_settings

    s = settings or get_settings()
    if not s.otel_exporter_otlp_endpoint:
        return NullMetrics()
    try:
        return OTelMetrics(s)
    except ImportError:
        import logging

        logging.getLogger("ikip_common").warning(
            "OTEL_EXPORTER_OTLP_ENDPOINT set but opentelemetry isn't installed; "
            "install the 'otel' group. Metrics disabled."
        )
        return NullMetrics()
