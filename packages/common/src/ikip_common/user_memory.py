"""Long-term memory — enrich retrieval, never the answer (ADR 0032 layer 2).

A per-(tenant, user) store of **preferences** (language, units, default document scope) and
**entities** (the filers/assets this user works with). It exists to do exactly two things:

1. **bias/filter retrieval** — derive `RetrievalFilters` from stored preferences (e.g. default the
   `document_type` / equipment scope, resolve "our usual supplier" to a known entity), and
2. **personalize presentation** — language/units for rendering.

It is **never** a source of answer content. This is the hard garde-fou of ADR 0032, and it is
enforced *structurally*, not by prompt discipline: the only retrieval-facing export here is
`memory_retrieval_filters`, which returns a `RetrievalFilters` (a WHERE clause) — it produces no
text, no evidence block, nothing the generator can cite. The grounding validator + citation
resolution are untouched: a claim with no retrieved citation is still dropped/abstained. A
remembered "fact" can only ever *narrow what we search*, so at worst it changes which cited chunks
surface — it can never become an uncited claim.

Tenant+user-scoped (NFR10); user-editable (it's their memory — `remember`/`forget`);
retention-governed (Story 6.5). CRUD is pure DB (no network), base-env safe.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ikip_common.db.models import UserMemory
from ikip_common.db.retrieval import RetrievalFilters

# Memory kinds (stored in UserMemory.kind).
KIND_PREFERENCE = "preference"
KIND_ENTITY = "entity"

# Preference keys that map onto a retrieval filter. Anything NOT in here is presentation-only
# (e.g. "language", "units") and never touches retrieval — an allow-list, so a new preference can't
# silently start steering retrieval without a deliberate change here.
PREF_DOCUMENT_TYPE = "document_type"  # -> RetrievalFilters.document_type
PREF_EQUIPMENT_ID = "equipment_id"  # -> RetrievalFilters.equipment_id (value: uuid string)
PREF_METADATA_SCOPE = "metadata_scope"  # -> merged into RetrievalFilters.metadata (JSONB subset)


@dataclass(frozen=True)
class MemoryEntry:
    """One remembered item, as returned to callers/the user (UI shows + lets them edit these)."""

    kind: str
    key: str
    value: dict


def remember(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    kind: str,
    key: str,
    value: dict,
) -> None:
    """Upsert one memory entry (user-editable). Idempotent on (tenant, user, kind, key)."""
    stmt = (
        pg_insert(UserMemory)
        .values(
            tenant_id=tenant_id,
            user_id=user_id,
            kind=kind,
            key=key,
            value=value,
        )
        .on_conflict_do_update(
            constraint="uq_user_memory",
            set_={"value": value},
        )
    )
    session.execute(stmt)


def forget(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    kind: str,
    key: str,
) -> None:
    """Delete one memory entry (user-editable). No-op if absent."""
    session.execute(
        delete(UserMemory).where(
            UserMemory.tenant_id == tenant_id,
            UserMemory.user_id == user_id,
            UserMemory.kind == kind,
            UserMemory.key == key,
        )
    )


def get_memory(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[MemoryEntry]:
    """All memory entries for (tenant, user), tenant+user-scoped (NFR10). Ordered for stable UI."""
    rows = session.execute(
        select(UserMemory)
        .where(UserMemory.tenant_id == tenant_id, UserMemory.user_id == user_id)
        .order_by(UserMemory.kind, UserMemory.key)
    ).scalars()
    return [MemoryEntry(kind=r.kind, key=r.key, value=dict(r.value or {})) for r in rows]


def _preferences(entries: Sequence[MemoryEntry]) -> dict[str, dict]:
    return {e.key: e.value for e in entries if e.kind == KIND_PREFERENCE}


def memory_retrieval_filters(
    entries: Sequence[MemoryEntry],
    *,
    base: RetrievalFilters | None = None,
) -> RetrievalFilters:
    """Derive `RetrievalFilters` from remembered **preferences** — the ONLY retrieval-facing use of
    memory (the garde-fou: memory -> filters, never evidence).

    An explicit value already set on `base` always wins (the current request is authoritative;
    memory only fills gaps / supplies defaults). Only the allow-listed preference keys map to a
    filter; presentation preferences (language/units) are ignored here by construction — they can't
    steer retrieval. Returns filters only: no text, nothing citable.
    """
    base = base or RetrievalFilters()
    prefs = _preferences(entries)

    document_type = base.document_type
    if document_type is None:
        pref_dt = prefs.get(PREF_DOCUMENT_TYPE, {}).get("value")
        if isinstance(pref_dt, str) and pref_dt:
            document_type = pref_dt

    equipment_id = base.equipment_id
    if equipment_id is None:
        pref_eq = prefs.get(PREF_EQUIPMENT_ID, {}).get("value")
        if isinstance(pref_eq, str) and pref_eq:
            try:
                equipment_id = uuid.UUID(pref_eq)
            except ValueError:
                equipment_id = None  # a malformed remembered id must never widen/break the query

    # metadata: start from the base request, then fill in remembered scope keys it didn't set.
    metadata = dict(base.metadata) if base.metadata else None
    pref_scope = prefs.get(PREF_METADATA_SCOPE, {}).get("value")
    if isinstance(pref_scope, dict) and pref_scope:
        merged = dict(pref_scope)
        if metadata:
            merged.update(metadata)  # request-provided keys win over remembered defaults
        metadata = merged

    return RetrievalFilters(
        current_only=base.current_only,
        document_type=document_type,
        equipment_id=equipment_id,
        user_id=base.user_id,
        metadata=metadata,
    )
