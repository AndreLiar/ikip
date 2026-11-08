"""add workspaces, memberships, and document ACL

Revision ID: b04d91a7e231
Revises: 9ca41e0d2b77
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b04d91a7e231"
down_revision: str | None = "9ca41e0d2b77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace",
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_workspace_tenant_name"),
    )
    op.create_index("ix_workspace_tenant_id", "workspace", ["tenant_id"])
    op.create_table(
        "workspace_membership",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", "manager", "technician", name="user_role", create_type=False),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("workspace_id", "user_id"),
    )
    op.create_table(
        "document_permission",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "user_id", "workspace_id", name="uq_document_permission_subject"
        ),
        sa.CheckConstraint(
            "(user_id IS NOT NULL) <> (workspace_id IS NOT NULL)",
            name="ck_document_permission_one_subject",
        ),
    )
    op.create_index("ix_document_permission_document_id", "document_permission", ["document_id"])
    op.create_index("ix_document_permission_tenant_id", "document_permission", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_document_permission_tenant_id", table_name="document_permission")
    op.drop_index("ix_document_permission_document_id", table_name="document_permission")
    op.drop_table("document_permission")
    op.drop_table("workspace_membership")
    op.drop_index("ix_workspace_tenant_id", table_name="workspace")
    op.drop_table("workspace")
