"""Persist visual elements (Epic 9, Story 9.1, ADR 0031).

Tenant-scoped insert of `VisualElement` rows from the extractor's DB-free specs, linked to their
`DocumentVersion` (and an optional `Section` for the back-reference, AC2). Low-confidence
detections are stored flagged for review. Caption + crop key are filled by later stages (9.2).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from ikip_common.db.models import VisualElement


def persist_visual_elements(
    session,  # noqa: ANN001 — SQLAlchemy Session
    tenant_id: uuid.UUID,
    document_version_id: uuid.UUID,
    specs: Sequence[Any],
    *,
    section_id: uuid.UUID | None = None,
) -> int:
    """Insert visual elements for a document version. Returns the number persisted. Caller
    commits. `specs` are duck-typed (kind/page/bbox/confidence/low_confidence)."""
    n = 0
    for s in specs:
        bbox = list(s.bbox) if s.bbox is not None else None
        session.add(
            VisualElement(
                tenant_id=tenant_id,
                document_version_id=document_version_id,
                section_id=section_id,
                kind=s.kind,
                page=s.page,
                bbox=bbox,
                confidence=s.confidence,
                low_confidence=bool(s.low_confidence),
            )
        )
        n += 1
    return n
