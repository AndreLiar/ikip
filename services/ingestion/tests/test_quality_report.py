"""Data-quality report tests (Story 2.6 AC2). Pure."""

from ikip_ingestion.quality_report import DataQualityReport


def test_rates_computed() -> None:
    r = DataQualityReport(
        total=10, succeeded=7, failed=2, dead_letter=1, duplicates=3, new_versions=4
    )
    assert r.success_rate == 0.7
    assert r.failure_rate == 0.3  # (failed + dead_letter) / total


def test_empty_report_safe() -> None:
    r = DataQualityReport()
    assert r.success_rate == 0.0
    assert r.failure_rate == 0.0


def test_as_dict_includes_rates() -> None:
    r = DataQualityReport(total=2, succeeded=1, failed=1)
    d = r.as_dict()
    assert d["success_rate"] == 0.5
    assert d["failure_rate"] == 0.5
    assert d["total"] == 2
