"""Ingestion-job repository + state transitions (Story 2.1).

Tenant-scoped (inherits isolation). Encodes the valid job lifecycle so state
changes are consistent: pending → running → (succeeded | failed) ; failed → running
(retry) ; failed → dead_letter.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ikip_common.db.models import IngestionJob, IngestionState
from ikip_common.db.repository import TenantScopedRepository

# Allowed state transitions (Story 2.6 dead-letter/retry builds on this).
_ALLOWED: dict[IngestionState, set[IngestionState]] = {
    IngestionState.pending: {IngestionState.running},
    IngestionState.running: {IngestionState.succeeded, IngestionState.failed},
    IngestionState.failed: {IngestionState.running, IngestionState.dead_letter},
    IngestionState.succeeded: set(),
    IngestionState.dead_letter: set(),
}


class IllegalStateTransitionError(Exception):
    pass


class IngestionJobRepository(TenantScopedRepository[IngestionJob]):
    model = IngestionJob

    def create(
        self,
        source: str,
        *,
        raw_object_key: str | None = None,
        content_type: str | None = None,
    ) -> IngestionJob:
        job = IngestionJob(source=source, raw_object_key=raw_object_key, content_type=content_type)
        return self.add(job)

    def transition(
        self,
        job: IngestionJob,
        to: IngestionState,
        *,
        error_info: dict | None = None,
    ) -> IngestionJob:
        if to not in _ALLOWED[job.state]:
            raise IllegalStateTransitionError(f"{job.state} -> {to} not allowed")
        now = datetime.now(UTC)
        if to is IngestionState.running:
            job.started_at = job.started_at or now
            job.attempts += 1
        if to in (IngestionState.succeeded, IngestionState.failed, IngestionState.dead_letter):
            job.finished_at = now
        if error_info is not None:
            job.error_info = error_info
        job.state = to
        return job
