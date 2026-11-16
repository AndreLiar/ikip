"""SEC XBRL structured-extraction tests (Epic 8, Story 8.1, ADR 0030). Pure — no network/DB."""

import pathlib
from datetime import date
from decimal import Decimal

from ikip_docproc.structured import FactSpec, SecCompanyFactsExtractor, StructuredExtractor

_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sec_companyfacts_mini.json"


def _facts() -> list[FactSpec]:
    return SecCompanyFactsExtractor().extract_facts(_FIXTURE.read_bytes())


def test_extractor_satisfies_port() -> None:
    assert isinstance(SecCompanyFactsExtractor(), StructuredExtractor)


def test_parses_duration_fact_with_exact_decimal() -> None:
    facts = _facts()
    rev = next(
        f
        for f in facts
        if f.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"
        and f.period_end == date(2023, 9, 30)
    )
    assert rev.value == Decimal("383285000000")  # exact, not float
    assert rev.period_start == date(2022, 9, 25)  # duration => start+end
    assert rev.unit == "USD" and rev.entity_cik == "0000320193"
    assert rev.form == "10-K" and rev.fiscal_year == 2023 and rev.frame == "CY2023"
    assert rev.accession == "0000320193-23-000106"  # provenance


def test_parses_instant_fact_as_period_start_none() -> None:
    facts = _facts()
    assets = next(f for f in facts if f.concept == "Assets")
    assert assets.period_start is None  # instant (balance sheet)
    assert assets.period_end == date(2023, 9, 30)
    assert assets.value == Decimal("352583000000")


def test_drops_malformed_and_filters_taxonomies() -> None:
    ext = SecCompanyFactsExtractor()  # default taxonomies: us-gaap, ffd (not dei)
    facts = ext.extract_facts(_FIXTURE.read_bytes())
    assert all(f.taxonomy == "us-gaap" for f in facts)  # dei filtered out
    assert ext.last_dropped == 1  # the null-value fact dropped (Story 8.1 AC4)
    assert all(f.value is not None for f in facts)


def test_dei_included_when_requested() -> None:
    facts = SecCompanyFactsExtractor(taxonomies=["us-gaap", "dei"]).extract_facts(
        _FIXTURE.read_bytes()
    )
    assert any(f.taxonomy == "dei" and f.unit == "shares" for f in facts)
