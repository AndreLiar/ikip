"""add fts and hnsw indexes

Revision ID: 3a15a5ad99fe
Revises: 1aa8f27570e7
Create Date: 2026-11-07 15:55:14.563790

Story 3.3 (ADR 0004): the two retrieval arms.
- chunk.content_tsv: a STORED generated tsvector ('simple' config — language-neutral,
  code/ref friendly, FTS_CONFIG) + GIN index -> BM25/full-text search.
- embedding.vector: an HNSW index with vector_cosine_ops -> semantic ANN search.
Hand-written to control the generated column and the pgvector/GIN index operators.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TSVECTOR

revision: str = "3a15a5ad99fe"
down_revision: str | None = "1aa8f27570e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FTS_CONFIG = "simple"


def upgrade() -> None:
    # Full-text arm: DB-generated, always-in-sync tsvector + GIN index.
    op.add_column(
        "chunk",
        sa.Column(
            "content_tsv",
            TSVECTOR,
            sa.Computed(f"to_tsvector('{FTS_CONFIG}', content)", persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_chunk_content_tsv", "chunk", ["content_tsv"], unique=False, postgresql_using="gin"
    )
    # Vector arm: HNSW approximate-nearest-neighbour index for cosine distance.
    op.create_index(
        "ix_embedding_vector_hnsw",
        "embedding",
        ["vector"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"vector": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_embedding_vector_hnsw", table_name="embedding")
    op.drop_index("ix_chunk_content_tsv", table_name="chunk")
    op.drop_column("chunk", "content_tsv")
