"""Structured-data extraction — financial facts from XBRL/SEC (Epic 8, Story 8.1, ADR 0030).

A `StructuredExtractor` port (mirrors `TextExtractor`) turns a structured filing into typed
`FactSpec`s — the exact figure + its period + provenance. The `SecCompanyFactsExtractor` parses
the SEC EDGAR *companyfacts* JSON (`data.sec.gov/api/xbrl/companyfacts/CIK##########.json`), which
pre-normalizes XBRL into `{facts: {taxonomy: {concept: {units: {unit: [fact, ...]}}}}}`.

Pure + deterministic (bytes in, FactSpecs out) — no network, no DB — so it is unit-testable.
Figures stay **exact**: values are parsed to `Decimal`, never float (ADR 0030).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class FactSpec:
    """A planned financial fact (DB-free): exact value + period + provenance (ADR 0030)."""

    entity_cik: str
    entity_name: str | None
    taxonomy: str
    concept: str
    value: Decimal
    unit: str
    period_end: date  # instant date, or the end of a duration
    period_start: date | None = None  # None => instant (balance-sheet) fact
    fiscal_year: int | None = None
    fiscal_period: str | None = None  # FY | Q1..Q4
    form: str | None = None  # 10-K | 10-Q
    filed_date: date | None = None
    frame: str | None = None
    accession: str = ""  # SEC accession number — the source filing (provenance, FR16)
    dimensions: dict = field(default_factory=dict)


@runtime_checkable
class StructuredExtractor(Protocol):
    """Port: raw structured filing bytes -> typed financial facts."""

    def extract_facts(self, data: bytes) -> list[FactSpec]: ...


def _to_decimal(v: object) -> Decimal | None:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _to_date(v: object) -> date | None:
    try:
        return date.fromisoformat(str(v))
    except (ValueError, TypeError):
        return None


class SecCompanyFactsExtractor:
    """Parse SEC EDGAR companyfacts JSON into FactSpecs. Validation drops malformed facts (no
    numeric value / no end date / no accession) rather than persisting ambiguous figures
    (Story 8.1 AC4); the count is available via `last_dropped`."""

    def __init__(self, taxonomies: Sequence[str] | None = None) -> None:
        # Default to the quantitative taxonomies; `dei` is mostly metadata.
        self._taxonomies = set(taxonomies) if taxonomies else {"us-gaap", "ffd"}
        self.last_dropped = 0

    def extract_facts(self, data: bytes) -> list[FactSpec]:
        doc = json.loads(data)
        cik = str(doc.get("cik", "")).zfill(10)
        name = doc.get("entityName")
        specs: list[FactSpec] = []
        dropped = 0
        for taxonomy, concepts in doc.get("facts", {}).items():
            if taxonomy not in self._taxonomies:
                continue
            for concept, body in concepts.items():
                for unit, items in body.get("units", {}).items():
                    for it in items:
                        val = _to_decimal(it.get("val"))
                        end = _to_date(it.get("end"))
                        accn = it.get("accn")
                        if val is None or end is None or not accn:
                            dropped += 1
                            continue
                        specs.append(
                            FactSpec(
                                entity_cik=cik,
                                entity_name=name,
                                taxonomy=taxonomy,
                                concept=concept,
                                value=val,
                                unit=unit,
                                period_end=end,
                                period_start=_to_date(it.get("start")),
                                fiscal_year=it.get("fy"),
                                fiscal_period=it.get("fp"),
                                form=it.get("form"),
                                filed_date=_to_date(it.get("filed")),
                                frame=it.get("frame"),
                                accession=str(accn),
                            )
                        )
        self.last_dropped = dropped
        return specs
