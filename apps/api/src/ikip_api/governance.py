"""Per-tenant quotas, API rate limits, and audit events (Story 4.8)."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, status
from ikip_common import get_settings
from ikip_common.auth import Principal
from ikip_common.db.models import UserRole
from pydantic import BaseModel

from ikip_api.auth import require_role

router = APIRouter(tags=["governance"])


class RateLimiter(Protocol):
    def consume(self, *, tenant_id: uuid.UUID, limit: int, window_s: int = 60) -> int: ...


class GovernanceService(Protocol):
    def authorize(self, principal: Principal, operation: str) -> None: ...
    def record(
        self,
        principal: Principal,
        operation: str,
        *,
        resource_type: str | None = None,
        resource_id: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> None: ...


class RedisRateLimiter:
    """Fixed-window limiter using one atomic Redis script."""

    _SCRIPT = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return n
"""

    def __init__(self) -> None:
        import redis

        self._client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)

    def consume(self, *, tenant_id: uuid.UUID, limit: int, window_s: int = 60) -> int:
        bucket = int(time.time()) // window_s
        count = int(self._client.eval(self._SCRIPT, 1, f"rate:{tenant_id}:{bucket}", window_s))
        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate limit exceeded",
                headers={"Retry-After": str(window_s)},
            )
        return count


class _DbGovernanceService:
    def __init__(self, limiter: RateLimiter) -> None:
        self._limiter = limiter

    def authorize(self, principal: Principal, operation: str) -> None:
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import AuditEvent, Tenant
        from sqlalchemy import func, select

        self._limiter.consume(
            tenant_id=principal.tenant_id,
            limit=get_settings().rate_limit_per_minute,
        )
        with make_session_factory()() as session:
            policies = (
                session.execute(
                    select(Tenant.policies).where(Tenant.id == principal.tenant_id)
                ).scalar_one_or_none()
                or {}
            )
            quota = (policies.get("quotas") or {}).get(operation)
            if quota is None:
                return
            start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            used = session.execute(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.tenant_id == principal.tenant_id,
                    AuditEvent.operation == operation,
                    AuditEvent.created_at >= start,
                )
            ).scalar_one()
            if used >= int(quota):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"daily quota exceeded for {operation}",
                )

    def record(
        self,
        principal: Principal,
        operation: str,
        *,
        resource_type: str | None = None,
        resource_id: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> None:
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import AuditEvent

        with make_session_factory()() as session:
            session.add(
                AuditEvent(
                    tenant_id=principal.tenant_id,
                    actor_user_id=principal.user_id,
                    operation=operation,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    event_metadata=metadata or {},
                )
            )
            session.commit()


def get_governance_service() -> GovernanceService:
    return _DbGovernanceService(RedisRateLimiter())


class AuditEventOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    operation: str
    resource_type: str | None
    resource_id: uuid.UUID | None
    metadata: dict
    created_at: datetime


@router.get("/audit-events", response_model=list[AuditEventOut])
def list_audit_events(
    principal: Annotated[Principal, Depends(require_role(UserRole.admin))],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditEventOut]:
    from ikip_common.db import make_session_factory
    from ikip_common.db.models import AuditEvent
    from sqlalchemy import select

    with make_session_factory()() as session:
        events = session.execute(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == principal.tenant_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
        ).scalars()
        return [
            AuditEventOut(
                id=event.id,
                actor_user_id=event.actor_user_id,
                operation=event.operation,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                metadata=event.event_metadata,
                created_at=event.created_at,
            )
            for event in events
        ]
