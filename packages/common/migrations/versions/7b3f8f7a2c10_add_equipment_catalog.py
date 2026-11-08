"""add equipment catalog and document associations

Revision ID: 7b3f8f7a2c10
Revises: 6dff50d415b4
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b3f8f7a2c10"
down_revision: str | None = "6dff50d415b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "equipment",
        sa.Column("manufacturer", sa.String(length=255), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("revision", sa.String(length=64), nullable=True),
        sa.Column("asset_id", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_equipment_tenant_id", "equipment", ["tenant_id"])
    op.create_index(
        "ix_equipment_tenant_model",
        "equipment",
        ["tenant_id", "manufacturer", "model", "revision"],
    )
    op.create_table(
        "document_equipment",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("equipment_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("document_id", "equipment_id"),
    )
    op.create_index("ix_document_equipment_equipment_id", "document_equipment", ["equipment_id"])


def downgrade() -> None:
    op.drop_index("ix_document_equipment_equipment_id", table_name="document_equipment")
    op.drop_table("document_equipment")
    op.drop_index("ix_equipment_tenant_model", table_name="equipment")
    op.drop_index("ix_equipment_tenant_id", table_name="equipment")
    op.drop_table("equipment")
