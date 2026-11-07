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
