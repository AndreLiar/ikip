"""add user_memory (ADR 0032 layer 2 — long-term memory)

Revision ID: f1c9a5e702b8
Revises: e8d3b14c7a92
Create Date: 2026-11-16

Per-(tenant,user) preferences + entities. Used ONLY to bias retrieval + personalize
presentation — never answer content (memory is not evidence). Tenant/user-scoped, user-editable.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f1c9a5e702b8"
down_revision: str | None = "e8d3b14c7a92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_memory",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", "kind", "key", name="uq_user_memory"),
    )
    op.create_index("ix_user_memory_tenant_user", "user_memory", ["tenant_id", "user_id"])
    op.create_index(op.f("ix_user_memory_tenant_id"), "user_memory", ["tenant_id"])
    op.create_index(op.f("ix_user_memory_user_id"), "user_memory", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_user_memory_user_id"), table_name="user_memory")
    op.drop_index(op.f("ix_user_memory_tenant_id"), table_name="user_memory")
    op.drop_index("ix_user_memory_tenant_user", table_name="user_memory")
    op.drop_table("user_memory")
