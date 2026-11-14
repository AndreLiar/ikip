"""Dagster wiring smoke test (Story 2.2 AC2).

Skipped unless Dagster is installed (it isn't in the fast `validate` CI job).
Run with: uv run --group dagster pytest services/ingestion/tests/test_definitions.py
Proves the Definitions load (asset + schedule) and the asset materializes
in-process (no tenant set -> safe no-op).
"""

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("dagster") is None, reason="dagster not installed"
)


def test_definitions_load_and_materialize() -> None:
    import dagster as dg
    from ikip_ingestion.definitions import defs, ingested_sources

    assert [s.name for s in defs.schedules] == ["daily_ingest"]

    result = dg.materialize([ingested_sources])
    assert result.success
    mats = result.asset_materializations_for_node("ingested_sources")
    md = {k: v.value for k, v in mats[0].metadata.items()}
    assert md == {"ingested": 0, "skipped": 0}  # no tenant configured -> no-op


def test_lineage_graph_raw_curated_versions() -> None:
    """Story 2.6 AC1: raw -> curated -> versions are chained Dagster assets."""
    from ikip_ingestion.definitions import defs

    keys = {k.to_user_string() for k in defs.resolve_asset_graph().get_all_asset_keys()}
    assert {"ingested_sources", "curated_documents", "document_versions"} <= keys


def test_asset_aware_rerun_of_curated_only() -> None:
    """Story 2.6 AC4: re-materialize a downstream asset without re-running upstream."""
    import dagster as dg
    from ikip_ingestion.definitions import curated_documents

    # Materialize ONLY the curated stage (Dagster allows selecting a subset).
    result = dg.materialize([curated_documents], selection=[curated_documents])
    assert result.success


def test_sensor_and_processing_job_registered() -> None:
    """ADR 0025: the event-shaped trigger (sensor) + its processing job are wired."""
    from ikip_ingestion.definitions import defs

    assert [s.name for s in defs.sensors] == ["pending_jobs_sensor"]


def test_pending_jobs_sensor_skips_without_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    """No tenant configured → the sensor is a clean no-op (no DB access)."""
    import dagster as dg
    import ikip_ingestion.definitions as d

    monkeypatch.setattr(d, "_DEFAULT_TENANT", "")
    result = d.pending_jobs_sensor(dg.build_sensor_context())
    assert isinstance(result, dg.SkipReason)


def test_watermark_decision_fires_once_per_new_batch() -> None:
    """ADR 0025: RunRequest on new work, SkipReason on nothing-new / nothing-pending."""
    import datetime as dt

    import dagster as dg
    from ikip_ingestion.definitions import _watermark_decision

    assert isinstance(_watermark_decision(None, None)[0], dg.SkipReason)  # nothing pending

    t1 = dt.datetime(2026, 11, 14, 9, 0, tzinfo=dt.UTC)
    decision, cursor = _watermark_decision(t1, None)  # new batch → fire
    assert isinstance(decision, dg.RunRequest)
    assert decision.run_key == t1.isoformat() == cursor

    # same watermark → dedup (a run is already draining this backlog)
    assert isinstance(_watermark_decision(t1, cursor)[0], dg.SkipReason)

    t2 = t1 + dt.timedelta(minutes=5)  # newer jobs arrived → fire again
    assert isinstance(_watermark_decision(t2, cursor)[0], dg.RunRequest)
