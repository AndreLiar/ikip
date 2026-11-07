"""Ingestion-job lifecycle tests (Story 2.1 AC2/AC4).

DB-backed → gated on TEST_DATABASE_URL (ephemeral Neon branch in CI; skipped
without it so `uv run pytest` stays green). Data via flush+rollback.
"""

import os

import pytest
from ikip_common.db.base import Base
from ikip_common.db.ingestion import IllegalStateTransitionError, IngestionJobRepository
from ikip_common.db.models import IngestionState, Tenant
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture(scope="module")
def engine():
    url = _URL.replace("postgresql://", "postgresql+psycopg://", 1) if _URL else _URL
    eng = create_engine(url)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s
        s.rollback()


def _repo(session: Session) -> tuple[IngestionJobRepository, object]:
    t = Tenant(name="T")
    session.add(t)
    session.flush()
    return IngestionJobRepository(session, t.id), t


def test_create_defaults_pending(session: Session) -> None:
    repo, _ = _repo(session)
    job = repo.create("s3://src/a.pdf", raw_object_key="raw/t/a.pdf")
    session.flush()
    assert job.state is IngestionState.pending
    assert job.attempts == 0
    assert job.raw_object_key == "raw/t/a.pdf"


def test_happy_path_transitions(session: Session) -> None:
    repo, _ = _repo(session)
    job = repo.create("src")
    session.flush()
    repo.transition(job, IngestionState.running)
    assert job.attempts == 1 and job.started_at is not None
    repo.transition(job, IngestionState.succeeded)
    assert job.state is IngestionState.succeeded and job.finished_at is not None


def test_retry_then_dead_letter(session: Session) -> None:
    repo, _ = _repo(session)
    job = repo.create("src")
    session.flush()
    repo.transition(job, IngestionState.running)
    repo.transition(job, IngestionState.failed, error_info={"err": "parse"})
    assert job.error_info == {"err": "parse"}
    repo.transition(job, IngestionState.running)  # retry
    assert job.attempts == 2
    repo.transition(job, IngestionState.failed)
    repo.transition(job, IngestionState.dead_letter)
    assert job.state is IngestionState.dead_letter


def test_illegal_transition_rejected(session: Session) -> None:
    repo, _ = _repo(session)
    job = repo.create("src")
    session.flush()
    with pytest.raises(IllegalStateTransitionError):
        repo.transition(job, IngestionState.succeeded)  # pending -> succeeded not allowed


def test_job_is_tenant_scoped(session: Session) -> None:
    repo_a, _ = _repo(session)
    repo_b, _ = _repo(session)
    repo_a.create("a")
    session.flush()
    assert len(repo_a.list()) == 1
    assert len(repo_b.list()) == 0  # other tenant sees nothing
