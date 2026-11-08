"""Cross-tenant organization lifecycle for explicitly configured platform operators."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from ikip_common.auth import Principal
from ikip_common.db.models import AccountStatus, UserRole
from pydantic import BaseModel, Field

from ikip_api.auth import require_platform_operator

router = APIRouter(prefix="/platform", tags=["platform"])
PlatformOperator = Annotated[Principal, Depends(require_platform_operator)]


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    admin_email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$")
    configuration: dict = Field(default_factory=dict)
    policies: dict = Field(default_factory=dict)


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    configuration: dict = Field(default_factory=dict)
    policies: dict = Field(default_factory=dict)


class PlatformOrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    configuration: dict
    policies: dict
    created_at: datetime


class PlatformAuditOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID
    operation: str
    target_tenant_id: uuid.UUID
    metadata: dict
    created_at: datetime


def _session():
    from ikip_common.db import make_session_factory

    return make_session_factory()()


def _organization(tenant) -> PlatformOrganizationOut:  # noqa: ANN001
    return PlatformOrganizationOut.model_validate(tenant, from_attributes=True)


def _audit(session, principal: Principal, operation: str, tenant_id: uuid.UUID, **metadata) -> None:  # noqa: ANN001
    from ikip_common.db.models import PlatformAuditEvent

    session.add(
        PlatformAuditEvent(
            actor_user_id=principal.user_id,
            operation=operation,
            target_tenant_id=tenant_id,
            event_metadata=metadata,
        )
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization not found")


@router.get("/organizations", response_model=list[PlatformOrganizationOut])
def list_organizations(principal: PlatformOperator) -> list[PlatformOrganizationOut]:
    from ikip_common.db.models import Tenant
    from sqlalchemy import select

    with _session() as session:
        tenants = session.execute(select(Tenant).order_by(Tenant.name, Tenant.id)).scalars()
        return [_organization(tenant) for tenant in tenants]


@router.post(
    "/organizations",
    response_model=PlatformOrganizationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    data: OrganizationCreate, principal: PlatformOperator
) -> PlatformOrganizationOut:
    from ikip_common.db.models import AppUser, Tenant

    with _session() as session:
        tenant = Tenant(
            name=data.name,
            configuration=data.configuration,
            policies=data.policies,
        )
        session.add(tenant)
        session.flush()
        session.add(
            AppUser(
                tenant_id=tenant.id,
                email=data.admin_email,
                role=UserRole.admin,
                account_status=AccountStatus.active,
            )
        )
        _audit(
            session,
            principal,
            "organization.create",
            tenant.id,
            name=data.name,
            admin_email=data.admin_email,
        )
        session.commit()
        return _organization(tenant)


@router.get("/organizations/{tenant_id}", response_model=PlatformOrganizationOut)
def get_organization(tenant_id: uuid.UUID, principal: PlatformOperator) -> PlatformOrganizationOut:
    from ikip_common.db.models import Tenant

    with _session() as session:
        tenant = session.get(Tenant, tenant_id)
        if tenant is None:
            raise _not_found()
        return _organization(tenant)


@router.put("/organizations/{tenant_id}", response_model=PlatformOrganizationOut)
def update_organization(
    tenant_id: uuid.UUID,
    data: OrganizationUpdate,
    principal: PlatformOperator,
) -> PlatformOrganizationOut:
    from ikip_common.db.models import Tenant

    with _session() as session:
        tenant = session.get(Tenant, tenant_id)
        if tenant is None:
            raise _not_found()
        previous_name = tenant.name
        tenant.name = data.name
        tenant.configuration = data.configuration
        tenant.policies = data.policies
        _audit(
            session,
            principal,
            "organization.update",
            tenant.id,
            previous_name=previous_name,
            name=data.name,
        )
        session.commit()
        return _organization(tenant)


@router.delete("/organizations/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(
    tenant_id: uuid.UUID,
    principal: PlatformOperator,
    confirm: Annotated[bool, Query()] = False,
    expected_name: Annotated[str | None, Query(max_length=255)] = None,
) -> Response:
    """Permanently delete a tenant and its cascaded data after two explicit confirmations."""
    from ikip_common.db.models import Tenant

    if not confirm or not expected_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="confirm=true and expected_name are required",
        )
    with _session() as session:
        tenant = session.get(Tenant, tenant_id)
        if tenant is None:
            raise _not_found()
        if tenant.name != expected_name:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="organization name confirmation does not match",
            )
        _audit(
            session,
            principal,
            "organization.delete",
            tenant.id,
            name=tenant.name,
        )
        session.delete(tenant)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/audit-events", response_model=list[PlatformAuditOut])
def list_platform_audit_events(
    principal: PlatformOperator,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[PlatformAuditOut]:
    from ikip_common.db.models import PlatformAuditEvent
    from sqlalchemy import select

    with _session() as session:
        events = session.execute(
            select(PlatformAuditEvent).order_by(PlatformAuditEvent.created_at.desc()).limit(limit)
        ).scalars()
        return [
            PlatformAuditOut(
                id=event.id,
                actor_user_id=event.actor_user_id,
                operation=event.operation,
                target_tenant_id=event.target_tenant_id,
                metadata=event.event_metadata,
                created_at=event.created_at,
            )
            for event in events
        ]
