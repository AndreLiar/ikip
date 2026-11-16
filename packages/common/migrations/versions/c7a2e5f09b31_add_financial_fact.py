"""add financial_fact (Epic 8, Story 8.1)

Revision ID: c7a2e5f09b31
Revises: b2f7a1c9d3e4
Create Date: 2026-11-16

ADR 0030: typed store for structured financial figures (XBRL/SEC). Exact value as NUMERIC
(never float), instant vs duration period, provenance via `accession` (+ optional
document_version_id), tenant-scoped. Modelled against real SEC EDGAR companyfacts.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c7a2e5f09b31"
down_revision: str | None = "b2f7a1c9d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_fact",
        sa.Column("entity_cik", sa.String(length=16), nullable=False),
        sa.Column("entity_name", sa.String(length=512), nullable=True),
        sa.Column("taxonomy", sa.String(length=32), nullable=False),
        sa.Column("concept", sa.String(length=256), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("dimensions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("value_numeric", sa.Numeric(precision=38, scale=6), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_period", sa.String(length=8), nullable=True),
        sa.Column("form", sa.String(length=16), nullable=True),
        sa.Column("filed_date", sa.Date(), nullable=True),
        sa.Column("frame", sa.String(length=32), nullable=True),
        sa.Column("accession", sa.String(length=32), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_version.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "entity_cik",
            "taxonomy",
            "concept",
            "unit",
            "period_start",
            "period_end",
            "accession",
            name="uq_financial_fact_identity",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_financial_fact_lookup",
        "financial_fact",
        ["tenant_id", "entity_cik", "concept", "period_end"],
        unique=False,
    )
    op.create_index(
        op.f("ix_financial_fact_tenant_id"), "financial_fact", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_financial_fact_document_version_id"),
        "financial_fact",
        ["document_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_financial_fact_document_version_id"), table_name="financial_fact")
    op.drop_index(op.f("ix_financial_fact_tenant_id"), table_name="financial_fact")
    op.drop_index("ix_financial_fact_lookup", table_name="financial_fact")
    op.drop_table("financial_fact")
