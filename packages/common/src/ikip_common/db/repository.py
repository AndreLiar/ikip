"""Tenant-scoped repository (Story 1.5 — the isolation mechanism, NFR10).

Every tenant-owned query goes through a repository bound to a single `tenant_id`.
The base class injects `WHERE tenant_id = :tenant_id` into every read and stamps
`tenant_id` on every write, so a repository for tenant A can never return or
touch tenant B's rows. This is defense at the application layer; Postgres RLS is
a planned defense-in-depth hardening (Epic 6, Story 6.2).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ikip_common.db.base import Base, TenantScoped


class TenantScopedRepository[ModelT: Base]:
    """Base repository that scopes all access to one tenant."""

    model: type[ModelT]

    def __init__(self, session: Session, tenant_id: uuid.UUID) -> None:
        if not issubclass(self.model, TenantScoped):
            raise TypeError(f"{self.model.__name__} is not TenantScoped")
        self.session = session
        self.tenant_id = tenant_id

    def _scoped(self):
        return select(self.model).where(self.model.tenant_id == self.tenant_id)

    def list(self) -> Sequence[ModelT]:
        return self.session.execute(self._scoped()).scalars().all()

    def get(self, id_: uuid.UUID) -> ModelT | None:
        stmt = self._scoped().where(self.model.id == id_)
        return self.session.execute(stmt).scalar_one_or_none()

    def add(self, obj: ModelT) -> ModelT:
        # Stamp tenant_id defensively — never trust a caller-supplied value.
        obj.tenant_id = self.tenant_id
        self.session.add(obj)
        return obj
