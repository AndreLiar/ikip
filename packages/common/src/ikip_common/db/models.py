"""Core tenant/user ORM models (Story 1.5).

Matches the data model in docs/architecture/lld/data-schema.md. More tables
(document, chunk, embedding, …) land with later epics; the tenant-scoping
pattern established here applies to all of them.
"""

from __future__ import annotations

import enum

from sqlalchemy import Enum, String, UniqueConstraint
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
