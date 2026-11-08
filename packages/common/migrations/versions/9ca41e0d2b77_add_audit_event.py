"""add audit event

Revision ID: 9ca41e0d2b77
Revises: 7b3f8f7a2c10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9ca41e0d2b77"
down_revision: str | None = "7b3f8f7a2c10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_event",
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("operation", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_event_actor_user_id", "audit_event", ["actor_user_id"])
    op.create_index("ix_audit_event_created_at", "audit_event", ["created_at"])
    op.create_index("ix_audit_event_operation", "audit_event", ["operation"])
    op.create_index("ix_audit_event_tenant_id", "audit_event", ["tenant_id"])
    op.create_index("ix_audit_tenant_time", "audit_event", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_tenant_time", table_name="audit_event")
    op.drop_index("ix_audit_event_tenant_id", table_name="audit_event")
    op.drop_index("ix_audit_event_operation", table_name="audit_event")
    op.drop_index("ix_audit_event_created_at", table_name="audit_event")
    op.drop_index("ix_audit_event_actor_user_id", table_name="audit_event")
    op.drop_table("audit_event")
