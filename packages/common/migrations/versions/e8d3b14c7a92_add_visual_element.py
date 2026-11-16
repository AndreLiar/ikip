"""add visual_element (Epic 9, Story 9.1)

Revision ID: e8d3b14c7a92
Revises: c7a2e5f09b31
Create Date: 2026-11-16

ADR 0031: diagrams / schematics / visual tables as retrievable evidence — page + bbox (the
region the viewer highlights), linked to Section/DocumentVersion, caption filled by
caption-and-embed (9.2), low-confidence flagged. Tenant-scoped.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e8d3b14c7a92"
down_revision: str | None = "c7a2e5f09b31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "visual_element",
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("caption", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("low_confidence", sa.Boolean(), nullable=False),
        sa.Column("crop_object_key", sa.String(length=2048), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_version.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["section_id"], ["section.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_visual_element_version_page",
        "visual_element",
        ["document_version_id", "page"],
        unique=False,
    )
    op.create_index(
        op.f("ix_visual_element_tenant_id"), "visual_element", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_visual_element_document_version_id"),
        "visual_element",
        ["document_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_visual_element_section_id"), "visual_element", ["section_id"], unique=False
    )
    op.create_index(
        op.f("ix_visual_element_low_confidence"),
        "visual_element",
        ["low_confidence"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_visual_element_low_confidence"), table_name="visual_element")
    op.drop_index(op.f("ix_visual_element_section_id"), table_name="visual_element")
    op.drop_index(op.f("ix_visual_element_document_version_id"), table_name="visual_element")
    op.drop_index(op.f("ix_visual_element_tenant_id"), table_name="visual_element")
    op.drop_index("ix_visual_element_version_page", table_name="visual_element")
    op.drop_table("visual_element")
