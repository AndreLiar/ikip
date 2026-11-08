"""add document_version source_object_key

Revision ID: 6dff50d415b4
Revises: 21448dfe68a6
Create Date: 2026-11-08 10:54:13.702540

Store the ORIGINAL source artifact key (raw tier) on a version so the source viewer
(Story 4.5) can serve the real PDF/HTML the user confirms evidence against, not just
the curated text. Nullable — existing rows keep NULL (the endpoint falls back to
curated_object_key). Plain String, reversible, no enum.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6dff50d415b4"
down_revision: str | None = "21448dfe68a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_version",
        sa.Column("source_object_key", sa.String(length=2048), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_version", "source_object_key")
