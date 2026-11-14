"""embedding vector -> halfvec (halve vector storage)

Revision ID: b2f7a1c9d3e4
Revises: d106483bdf6e
Create Date: 2026-11-14

ADR 0015/0027 storage lever: the `embedding` table dominated Neon (655 MB of 512-dim
float32 vectors + HNSW index). `halfvec` stores 16-bit floats → ~half the size with
negligible cosine-ANN recall loss. We cast IN PLACE (no re-embedding) and rebuild the HNSW
index with `halfvec_cosine_ops`. Reversible (cast back to `vector`).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b2f7a1c9d3e4"
down_revision: str | None = "d106483bdf6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The HNSW opclass is type-specific, so drop → alter type (in-place cast) → recreate.
    op.drop_index("ix_embedding_vector_hnsw", table_name="embedding")
    op.execute(
        "ALTER TABLE embedding ALTER COLUMN vector TYPE halfvec(512) USING vector::halfvec(512)"
    )
    op.execute(
        "CREATE INDEX ix_embedding_vector_hnsw ON embedding "
        "USING hnsw (vector halfvec_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_embedding_vector_hnsw", table_name="embedding")
    op.execute(
        "ALTER TABLE embedding ALTER COLUMN vector TYPE vector(512) USING vector::vector(512)"
    )
    op.execute(
        "CREATE INDEX ix_embedding_vector_hnsw ON embedding USING hnsw (vector vector_cosine_ops)"
    )
