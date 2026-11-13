"""add ingestion_job curated artifact keys

Revision ID: d106483bdf6e
Revises: f3b1094524b9
Create Date: 2026-11-13

Story 2.6 faithful lineage split: the `curated_documents` asset (extract+clean+validate)
writes the curated + layout artifacts to R2 and records their keys on the job; the
`document_versions` asset consumes them (versioning only, no re-extraction). A PENDING job
with curated_object_key set = "curated, awaiting versioning". Plain nullable Strings;
reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d106483bdf6e"
down_revision: str | None = "f3b1094524b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ingestion_job", sa.Column("curated_object_key", sa.String(length=2048)))
    op.add_column("ingestion_job", sa.Column("layout_object_key", sa.String(length=2048)))


def downgrade() -> None:
    op.drop_column("ingestion_job", "layout_object_key")
    op.drop_column("ingestion_job", "curated_object_key")
