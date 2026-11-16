"""Persist structured financial facts (Epic 8, Story 8.1, ADR 0030).

Tenant-scoped insert of `FinancialFact` rows from the extractor's DB-free fact records. Idempotent
on the `(tenant, entity, concept, period, unit, accession)` identity: re-ingesting a filing does
not duplicate facts (ON CONFLICT DO NOTHING). Values stay exact (`Decimal` → `NUMERIC`).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, Protocol

from sqlalchemy.dialects.postgresql import insert as pg_insert

from ikip_common.db.models import FinancialFact


class _FactLike(Protocol):
    entity_cik: str
    entity_name: str | None
    taxonomy: str
    concept: str
    value: Any
    unit: str
    period_end: Any
    period_start: Any
    fiscal_year: int | None
    fiscal_period: str | None
    form: str | None
    filed_date: Any
    frame: str | None
    accession: str
    dimensions: dict


def persist_facts(
    session,  # noqa: ANN001 — SQLAlchemy Session
    tenant_id: uuid.UUID,
    specs: Sequence[_FactLike],
    *,
    document_version_id: uuid.UUID | None = None,
) -> int:
    """Insert facts for a tenant; skip rows that already exist (identity conflict). Returns the
    number of NEW rows persisted. Caller commits."""
    if not specs:
        return 0
    # Dedupe within the batch by identity: a single INSERT can't ON CONFLICT against its own
    # duplicate rows, so collapse them here (keep first). Cross-call dedup (re-ingest) is handled
    # by ON CONFLICT DO NOTHING against the table's NULLS-NOT-DISTINCT unique constraint.
    seen: set[tuple] = set()
    rows = []
    for s in specs:
        key = (
            s.entity_cik,
            s.taxonomy,
            s.concept,
            s.unit,
            s.period_start,
            s.period_end,
            s.accession,
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "entity_cik": s.entity_cik,
                "entity_name": s.entity_name,
                "taxonomy": s.taxonomy,
                "concept": s.concept,
                "value_numeric": s.value,
                "unit": s.unit,
                "period_start": s.period_start,
                "period_end": s.period_end,
                "dimensions": s.dimensions,
                "fiscal_year": s.fiscal_year,
                "fiscal_period": s.fiscal_period,
                "form": s.form,
                "filed_date": s.filed_date,
                "frame": s.frame,
                "accession": s.accession,
                "document_version_id": document_version_id,
            }
        )
    # RETURNING, not rowcount: on_conflict_do_nothing reports rowcount=-1, so count the rows that
    # were actually inserted (conflicts are silently skipped).
    stmt = (
        pg_insert(FinancialFact)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_financial_fact_identity")
        .returning(FinancialFact.id)
    )
    return len(session.execute(stmt).all())
