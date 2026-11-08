"""add document version layout sidecar

Revision ID: c51e82a4f190
Revises: b04d91a7e231
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c51e82a4f190"
down_revision: str | None = "b04d91a7e231"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_version", sa.Column("layout_object_key", sa.String(2048), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("document_version", "layout_object_key")
