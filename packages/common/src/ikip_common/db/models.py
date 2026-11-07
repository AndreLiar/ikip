"""Core tenant/user ORM models (Story 1.5).

Matches the data model in docs/architecture/lld/data-schema.md. More tables
(document, chunk, embedding, …) land with later epics; the tenant-scoping
pattern established here applies to all of them.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ikip_common.db.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey


class UserRole(enum.StrEnum):
    admin = "admin"
    manager = "manager"
    technician = "technician"


class AccountStatus(enum.StrEnum):
    active = "active"
    suspended = "suspended"


class IngestionState(enum.StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    dead_letter = "dead_letter"


class Tenant(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "tenant"

    name: Mapped[str] = mapped_column(String(255))
    configuration: Mapped[dict] = mapped_column(JSONB, default=dict)
    policies: Mapped[dict] = mapped_column(JSONB, default=dict)


class AppUser(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    __tablename__ = "app_user"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_app_user_tenant_email"),)

    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), default=UserRole.technician
    )
    account_status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, name="account_status"), default=AccountStatus.active
    )


class IngestionJob(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Tracks one source file through ingestion (Story 2.1, FR8)."""

    __tablename__ = "ingestion_job"

    source: Mapped[str] = mapped_column(String(1024))
    state: Mapped[IngestionState] = mapped_column(
        Enum(IngestionState, name="ingestion_state"),
        default=IngestionState.pending,
        index=True,
    )
    # Key of the stored raw artifact in object storage (tier-prefixed), if captured.
    raw_object_key: Mapped[str | None] = mapped_column(String(2048), default=None)
    attempts: Mapped[int] = mapped_column(default=0)
    error_info: Mapped[dict | None] = mapped_column(JSONB, default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
