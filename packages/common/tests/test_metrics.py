"""Metrics port + Grafana artifacts (Story 5.6). Pure: no OTLP, no network."""

from __future__ import annotations

import json
from pathlib import Path

from ikip_common.config import Settings
from ikip_common.telemetry.metrics import FakeMetrics, NullMetrics, build_metrics

_ROOT = Path(__file__).resolve().parents[3]  # repo root


def _settings(**over) -> Settings:
    base = {
        "DATABASE_URL": "postgresql://u:p@h/db",
        "R2_ACCOUNT_ID": "a",
        "R2_ENDPOINT": "https://a.r2.cloudflarestorage.com",
        "R2_BUCKET": "b",
        "R2_ACCESS_KEY_ID": "ak",
        "R2_SECRET_ACCESS_KEY": "sk",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_SECRET": "x" * 36,
        "OTEL_EXPORTER_OTLP_ENDPOINT": None,
    }
    base.update(over)
    return Settings(**base)


def test_build_metrics_is_null_without_otlp_endpoint() -> None:
    assert isinstance(build_metrics(_settings()), NullMetrics)


def test_fake_metrics_records_requests_cost_and_gauges() -> None:
    m = FakeMetrics()
    m.record_request(operation="ask", latency_ms=12.5, status="answered")
    m.record_cost(cost_usd=0.001)
    m.set_eval_gauge("recall_at_k_mean", 1.0)
    assert m.requests[0] == {"operation": "ask", "latency_ms": 12.5, "status": "answered"}
    assert m.costs[0]["cost_usd"] == 0.001
    assert m.gauges["recall_at_k_mean"] == 1.0
    m.flush()  # no-op, must not raise


# --- Grafana artifacts are valid + wired to the metric names we emit -------


def test_ops_dashboard_is_valid_and_queries_our_metrics() -> None:
    doc = json.loads((_ROOT / "grafana/dashboards/ops.json").read_text())
    assert doc["uid"] == "ikip-ops"
    exprs = " ".join(t["expr"] for p in doc["panels"] for t in p.get("targets", []))
    assert "ikip_request_duration_ms_bucket" in exprs  # p95 latency
    assert "ikip_requests_total" in exprs  # throughput + error rate
    assert "ikip_request_cost_usd_total" in exprs  # cost


def test_eval_dashboard_queries_quality_gauges() -> None:
    doc = json.loads((_ROOT / "grafana/dashboards/eval.json").read_text())
    exprs = " ".join(t["expr"] for p in doc["panels"] for t in p.get("targets", []))
    for metric in ("recall_at_k_mean", "citation_grounding_coverage_mean", "behavior_conformity"):
        assert metric in exprs


def test_alert_rules_cover_ops_and_quality() -> None:
    text = (_ROOT / "grafana/alerts/rules.yaml").read_text()
    for alert in (
        "IkipHighLatencyP95",
        "IkipHighErrorRate",
        "IkipTokenCostSpike",
        "IkipGroundednessRegression",
        "IkipBehaviorConformityRegression",
    ):
        assert alert in text


def test_k6_script_exists_with_slo_thresholds() -> None:
    text = (_ROOT / "load/k6/ask_load.js").read_text()
    assert "p(95)<3000" in text and "ask_errors" in text and "/api/v1/ask" in text
