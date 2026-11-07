"""add evaluation_case

Revision ID: 5dc78f93f29b
Revises: 3a15a5ad99fe
Create Date: 2026-11-07 17:32:06.509765

Story 3.6 (ADR 0016): tenant-scoped gold-set cases for RAG evaluation. `case_key` is
stable within a `gold_set_version` (regression attribution). `expected_behavior` is a
plain String (not a DB enum) to keep the migration trap-free.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5dc78f93f29b"
down_revision: str | None = "3a15a5ad99fe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_case",
        sa.Column("case_key", sa.String(length=128), nullable=False),
        sa.Column("gold_set_version", sa.String(length=64), nullable=False),
        sa.Column("question", sa.String(), nullable=False),
        sa.Column("expected_behavior", sa.String(length=16), nullable=False),
        sa.Column("relevant_chunk_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notes", sa.String(length=1024), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "gold_set_version", "case_key", name="uq_eval_case_key"),
    )
    op.create_index(
        op.f("ix_evaluation_case_case_key"), "evaluation_case", ["case_key"], unique=False
    )
    op.create_index(
        op.f("ix_evaluation_case_gold_set_version"),
        "evaluation_case",
        ["gold_set_version"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_case_tenant_id"), "evaluation_case", ["tenant_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_evaluation_case_tenant_id"), table_name="evaluation_case")
    op.drop_index(op.f("ix_evaluation_case_gold_set_version"), table_name="evaluation_case")
    op.drop_index(op.f("ix_evaluation_case_case_key"), table_name="evaluation_case")
    op.drop_table("evaluation_case")
