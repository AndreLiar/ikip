"""add query_trace

Revision ID: f3b1094524b9
Revises: 11cb77b63d16
Create Date: 2026-11-11 03:53:49.968261

Story 5.4: durable end-to-end query→answer record (user, retrieval IDs, model, latency,
cost, Langfuse trace_id). Stores a query HASH + chunk IDs, not raw text (AC4). Plain
Strings/JSONB, no enum; reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3b1094524b9"
down_revision: str | None = "11cb77b63d16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "query_trace",
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=True),
        sa.Column("retrieved_chunk_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_query_trace_actor_user_id", "query_trace", ["actor_user_id"])
    op.create_index("ix_query_trace_conversation_id", "query_trace", ["conversation_id"])
    op.create_index("ix_query_trace_message_id", "query_trace", ["message_id"])
    op.create_index("ix_query_trace_operation", "query_trace", ["operation"])
    op.create_index("ix_query_trace_query_hash", "query_trace", ["query_hash"])
    op.create_index("ix_query_trace_trace_id", "query_trace", ["trace_id"])
    op.create_index("ix_query_trace_tenant_id", "query_trace", ["tenant_id"])
    op.create_index("ix_query_trace_created_at", "query_trace", ["created_at"])
    op.create_index("ix_query_trace_tenant_time", "query_trace", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_table("query_trace")
