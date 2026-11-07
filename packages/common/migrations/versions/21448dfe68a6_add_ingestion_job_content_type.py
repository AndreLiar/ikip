"""add ingestion_job content_type

Revision ID: 21448dfe68a6
Revises: 5dc78f93f29b
Create Date: 2026-11-07 21:44:06.863257

Persist the raw artifact's MIME type on the job (Story 2.2), so curation doesn't
have to sniff HTML later. Nullable — existing jobs keep NULL (curation falls back
to content sniffing). Plain String, no enum (trap-free, reversible).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "21448dfe68a6"
down_revision: str | None = "5dc78f93f29b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ingestion_job", sa.Column("content_type", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("ingestion_job", "content_type")
