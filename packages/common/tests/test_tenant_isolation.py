"""Tenant-isolation tests (Story 1.5 AC4).

These need a real Postgres. They run against the DB in `TEST_DATABASE_URL`
(in CI: an ephemeral Neon branch; locally: a throwaway branch/DB) — NOT the
shared dev DB. Skipped if unset, so `uv run pytest` stays green without a DB.

Data is created with `flush()` + `rollback()` (never committed), and the schema
is created/dropped per module, so the target DB is left clean.
"""

import os
import uuid

import pytest
from ikip_common.db.base import Base
from ikip_common.db.models import AppUser, Tenant, UserRole
from ikip_common.db.repository import TenantScopedRepository
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

_TEST_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not _TEST_URL, reason="TEST_DATABASE_URL not set (ephemeral test DB required)"
)


class UserRepo(TenantScopedRepository[AppUser]):
    model = AppUser


@pytest.fixture(scope="module")
def engine():
    url = _TEST_URL
    if url and url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    eng = create_engine(url)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s
        s.rollback()  # never persist test data


def _seed(session: Session) -> tuple[Tenant, Tenant]:
    a, b = Tenant(name="Tenant A"), Tenant(name="Tenant B")
    session.add_all([a, b])
    session.flush()
    session.add_all(
        [
            AppUser(tenant_id=a.id, email="admin@a.com", role=UserRole.admin),
            AppUser(tenant_id=a.id, email="tech@a.com", role=UserRole.technician),
            AppUser(tenant_id=b.id, email="admin@b.com", role=UserRole.admin),
        ]
    )
    session.flush()
    return a, b


def test_repo_lists_only_own_tenant(session: Session) -> None:
    a, b = _seed(session)
    emails = {u.email for u in UserRepo(session, a.id).list()}
    assert emails == {"admin@a.com", "tech@a.com"}  # none of B's


def test_repo_cannot_get_other_tenant_row(session: Session) -> None:
    a, b = _seed(session)
    b_user = next(u for u in UserRepo(session, b.id).list())
    # A repo scoped to tenant A must not be able to fetch tenant B's row by id.
    assert UserRepo(session, a.id).get(b_user.id) is None


def test_add_stamps_tenant_id(session: Session) -> None:
    a, _ = _seed(session)
    # Even if a caller tries to set a foreign tenant_id, the repo overrides it.
    u = AppUser(tenant_id=uuid.uuid4(), email="x@a.com", role=UserRole.manager)
    UserRepo(session, a.id).add(u)
    session.flush()
    assert u.tenant_id == a.id
