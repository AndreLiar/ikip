"""Database layer: models, session, tenant-scoped repository (Story 1.5)."""

from ikip_common.db.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey
from ikip_common.db.ingestion import IllegalStateTransitionError, IngestionJobRepository
from ikip_common.db.models import (
    AccountStatus,
    AppUser,
    IngestionJob,
    IngestionState,
    Tenant,
    UserRole,
)
from ikip_common.db.repository import TenantScopedRepository
from ikip_common.db.session import make_engine, make_session_factory

__all__ = [
    "Base",
    "TenantScoped",
    "Timestamped",
    "UUIDPrimaryKey",
    "Tenant",
    "AppUser",
    "UserRole",
    "AccountStatus",
    "IngestionJob",
    "IngestionState",
    "IngestionJobRepository",
    "IllegalStateTransitionError",
    "TenantScopedRepository",
    "make_engine",
    "make_session_factory",
]
