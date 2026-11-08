"""add platform operator audit event

Revision ID: d62f31b8a405
Revises: c51e82a4f190
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d62f31b8a405"
down_revision: str | None = "c51e82a4f190"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_audit_event",
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(128), nullable=False),
        sa.Column("target_tenant_id", sa.Uuid(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("actor_user_id", "operation", "target_tenant_id", "created_at"):
        op.create_index(f"ix_platform_audit_event_{column}", "platform_audit_event", [column])


def downgrade() -> None:
    for column in reversed(("actor_user_id", "operation", "target_tenant_id", "created_at")):
        op.drop_index(f"ix_platform_audit_event_{column}", table_name="platform_audit_event")
    op.drop_table("platform_audit_event")
