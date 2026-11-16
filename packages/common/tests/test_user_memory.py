"""Long-term memory tests (ADR 0032 layer 2). Two parts:

- pure: `memory_retrieval_filters` derivation + the hard garde-fou (memory -> filters, never
  evidence) — no DB, run in the base `validate` CI env.
- DB-backed: CRUD + tenant/user scoping — gated on TEST_DATABASE_URL (throwaway pg). flush+rollback.
"""

import os
import uuid

import pytest
from ikip_common.db.retrieval import RetrievalFilters
from ikip_common.user_memory import (
    KIND_ENTITY,
    KIND_PREFERENCE,
    PREF_DOCUMENT_TYPE,
    PREF_EQUIPMENT_ID,
    PREF_METADATA_SCOPE,
    MemoryEntry,
    memory_retrieval_filters,
)

# ---------------------------------------------------------------------------- pure: derivation


def _pref(key: str, value) -> MemoryEntry:  # noqa: ANN001
    return MemoryEntry(kind=KIND_PREFERENCE, key=key, value={"value": value})


def test_empty_memory_yields_default_filters() -> None:
    out = memory_retrieval_filters([])
    assert out == RetrievalFilters()


def test_document_type_preference_biases_retrieval() -> None:
    out = memory_retrieval_filters([_pref(PREF_DOCUMENT_TYPE, "manual")])
    assert out.document_type == "manual"


def test_equipment_preference_parsed_to_uuid() -> None:
    eq = uuid.uuid4()
    out = memory_retrieval_filters([_pref(PREF_EQUIPMENT_ID, str(eq))])
    assert out.equipment_id == eq


def test_malformed_equipment_id_is_ignored_not_raised() -> None:
    # A bad remembered value must never widen or break the query — it is simply dropped.
    out = memory_retrieval_filters([_pref(PREF_EQUIPMENT_ID, "not-a-uuid")])
    assert out.equipment_id is None


def test_metadata_scope_preference_merged() -> None:
    out = memory_retrieval_filters([_pref(PREF_METADATA_SCOPE, {"plant": "lyon"})])
    assert out.metadata == {"plant": "lyon"}


def test_request_filters_win_over_memory() -> None:
    # Memory only fills gaps; an explicit request value is authoritative.
    base = RetrievalFilters(document_type="drawing", metadata={"plant": "paris"})
    out = memory_retrieval_filters(
        [_pref(PREF_DOCUMENT_TYPE, "manual"), _pref(PREF_METADATA_SCOPE, {"plant": "lyon"})],
        base=base,
    )
    assert out.document_type == "drawing"
    assert out.metadata == {"plant": "paris"}  # request key wins over remembered default


# ----------------------------------------------------------------- pure: the hard garde-fou

PRESENTATION_ONLY_KEYS = ["language", "units"]


def test_presentation_preferences_never_touch_retrieval() -> None:
    # language/units are presentation-only — not on the retrieval allow-list, so filters stay base.
    entries = [_pref("language", "fr"), _pref("units", "metric")]
    assert memory_retrieval_filters(entries) == RetrievalFilters()


def test_remembered_entity_can_only_narrow_search_never_become_content() -> None:
    # The garde-fou: the ONLY retrieval-facing output of memory is a RetrievalFilters (a WHERE
    # clause). A remembered "entity"/"fact" produces NO text and nothing citable — at most it
    # narrows which (still-cited) chunks surface. We assert the output type carries no answer
    # content: it is a set of structural filters, period.
    remembered_fact = MemoryEntry(
        kind=KIND_ENTITY,
        key="usual_supplier",
        value={"value": "ACME Corp", "note": "revenue was $5B last year"},
    )
    out = memory_retrieval_filters([remembered_fact])
    assert isinstance(out, RetrievalFilters)
    # No field of the derived filter carries the remembered free-text claim.
    assert "revenue was $5B" not in repr(out)
    # An entity (not a preference) doesn't even map to a filter here — it's inert for retrieval
    # unless explicitly modelled as a scope preference.
    assert out == RetrievalFilters()


# ----------------------------------------------------------------------- DB-backed: CRUD + scoping

_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture(scope="module")
def engine():  # noqa: ANN201
    from ikip_common.db.base import Base
    from sqlalchemy import create_engine

    url = _URL.replace("postgresql://", "postgresql+psycopg://", 1) if _URL else _URL
    eng = create_engine(url)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def session(engine):  # noqa: ANN001, ANN201
    from sqlalchemy.orm import Session

    with Session(engine) as s:
        yield s
        s.rollback()


def _tenant(session):  # noqa: ANN001, ANN202
    from ikip_common.db.models import Tenant

    t = Tenant(name="Mem")
    session.add(t)
    session.flush()
    return t.id


def test_remember_get_forget_roundtrip(session) -> None:  # noqa: ANN001
    from ikip_common.user_memory import forget, get_memory, remember

    tid = _tenant(session)
    uid = uuid.uuid4()
    remember(
        session,
        tenant_id=tid,
        user_id=uid,
        kind=KIND_PREFERENCE,
        key=PREF_DOCUMENT_TYPE,
        value={"value": "manual"},
    )
    session.flush()
    entries = get_memory(session, tenant_id=tid, user_id=uid)
    assert entries == [
        MemoryEntry(kind=KIND_PREFERENCE, key=PREF_DOCUMENT_TYPE, value={"value": "manual"})
    ]

    # upsert is idempotent and updates the value in place (user editing their memory)
    remember(
        session,
        tenant_id=tid,
        user_id=uid,
        kind=KIND_PREFERENCE,
        key=PREF_DOCUMENT_TYPE,
        value={"value": "drawing"},
    )
    session.flush()
    entries = get_memory(session, tenant_id=tid, user_id=uid)
    assert len(entries) == 1
    assert entries[0].value == {"value": "drawing"}

    forget(session, tenant_id=tid, user_id=uid, kind=KIND_PREFERENCE, key=PREF_DOCUMENT_TYPE)
    session.flush()
    assert get_memory(session, tenant_id=tid, user_id=uid) == []


def test_memory_is_tenant_and_user_scoped(session) -> None:  # noqa: ANN001
    from ikip_common.user_memory import get_memory, remember

    tid = _tenant(session)
    uid_a, uid_b = uuid.uuid4(), uuid.uuid4()
    remember(
        session,
        tenant_id=tid,
        user_id=uid_a,
        kind=KIND_PREFERENCE,
        key="language",
        value={"value": "fr"},
    )
    session.flush()
    # a different user in the same tenant sees nothing (NFR10)
    assert get_memory(session, tenant_id=tid, user_id=uid_b) == []
    assert len(get_memory(session, tenant_id=tid, user_id=uid_a)) == 1
