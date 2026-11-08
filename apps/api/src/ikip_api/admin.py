"""Tenant administration: organization, users, workspaces and document ACLs (Story 4.7)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from ikip_common.auth import Principal
from ikip_common.db.models import AccountStatus, UserRole
from pydantic import BaseModel, Field, model_validator

from ikip_api.auth import require_role
from ikip_api.governance import GovernanceService, get_governance_service

router = APIRouter(prefix="/admin", tags=["administration"])
AdminPrincipal = Annotated[Principal, Depends(require_role(UserRole.admin))]
ManagerPrincipal = Annotated[Principal, Depends(require_role(UserRole.manager))]
Governance = Annotated[GovernanceService, Depends(get_governance_service)]


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    policies: dict


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    policies: dict = Field(default_factory=dict)


class UserWrite(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$")
    role: UserRole = UserRole.technician
    account_status: AccountStatus = AccountStatus.active


class UserOut(UserWrite):
    id: uuid.UUID


class WorkspaceWrite(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class WorkspaceOut(WorkspaceWrite):
    id: uuid.UUID


class MembershipWrite(BaseModel):
    user_id: uuid.UUID
    role: UserRole = UserRole.technician


class PermissionWrite(BaseModel):
    user_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def one_subject(self):
        if (self.user_id is None) == (self.workspace_id is None):
            raise ValueError("exactly one of user_id or workspace_id is required")
        return self


class PermissionOut(PermissionWrite):
    id: uuid.UUID
    document_id: uuid.UUID


def _session():
    from ikip_common.db import make_session_factory

    return make_session_factory()()


def _missing() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource not found")


@router.get("/organization", response_model=OrganizationOut)
def get_organization(principal: AdminPrincipal) -> OrganizationOut:
    from ikip_common.db.models import Tenant

    with _session() as session:
        tenant = session.get(Tenant, principal.tenant_id)
        if tenant is None:
            raise _missing()
        return OrganizationOut(id=tenant.id, name=tenant.name, policies=tenant.policies)


@router.put("/organization", response_model=OrganizationOut)
def update_organization(
    data: OrganizationUpdate, principal: AdminPrincipal, governance: Governance
) -> OrganizationOut:
    from ikip_common.db.models import Tenant

    governance.authorize(principal, "organization.update")
    with _session() as session:
        tenant = session.get(Tenant, principal.tenant_id)
        if tenant is None:
            raise _missing()
        tenant.name, tenant.policies = data.name, data.policies
        session.commit()
        result = OrganizationOut(id=tenant.id, name=tenant.name, policies=tenant.policies)
    governance.record(
        principal, "organization.update", resource_type="tenant", resource_id=principal.tenant_id
    )
    return result


@router.get("/users", response_model=list[UserOut])
def list_users(principal: ManagerPrincipal) -> list[UserOut]:
    from ikip_common.db.models import AppUser
    from sqlalchemy import select

    with _session() as session:
        users = session.execute(
            select(AppUser).where(AppUser.tenant_id == principal.tenant_id).order_by(AppUser.email)
        ).scalars()
        return [UserOut.model_validate(user, from_attributes=True) for user in users]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(data: UserWrite, principal: AdminPrincipal, governance: Governance) -> UserOut:
    from ikip_common.db.models import AppUser

    governance.authorize(principal, "user.create")
    with _session() as session:
        user = AppUser(tenant_id=principal.tenant_id, **data.model_dump())
        session.add(user)
        session.commit()
        result = UserOut.model_validate(user, from_attributes=True)
    governance.record(principal, "user.create", resource_type="user", resource_id=result.id)
    return result


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID, data: UserWrite, principal: AdminPrincipal, governance: Governance
) -> UserOut:
    from ikip_common.db.models import AppUser
    from sqlalchemy import select

    governance.authorize(principal, "user.update")
    with _session() as session:
        user = session.execute(
            select(AppUser).where(AppUser.id == user_id, AppUser.tenant_id == principal.tenant_id)
        ).scalar_one_or_none()
        if user is None:
            raise _missing()
        for key, value in data.model_dump().items():
            setattr(user, key, value)
        session.commit()
        result = UserOut.model_validate(user, from_attributes=True)
    governance.record(principal, "user.update", resource_type="user", resource_id=user_id)
    return result


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: uuid.UUID, principal: AdminPrincipal, governance: Governance) -> Response:
    from ikip_common.db.models import AppUser
    from sqlalchemy import delete

    governance.authorize(principal, "user.delete")
    with _session() as session:
        result = session.execute(
            delete(AppUser).where(AppUser.id == user_id, AppUser.tenant_id == principal.tenant_id)
        )
        if result.rowcount == 0:
            raise _missing()
        session.commit()
    governance.record(principal, "user.delete", resource_type="user", resource_id=user_id)
    return Response(status_code=204)


@router.get("/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(principal: ManagerPrincipal) -> list[WorkspaceOut]:
    from ikip_common.db.models import Workspace
    from sqlalchemy import select

    with _session() as session:
        rows = session.execute(
            select(Workspace)
            .where(Workspace.tenant_id == principal.tenant_id)
            .order_by(Workspace.name)
        ).scalars()
        return [WorkspaceOut.model_validate(row, from_attributes=True) for row in rows]


@router.post("/workspaces", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    data: WorkspaceWrite, principal: ManagerPrincipal, governance: Governance
) -> WorkspaceOut:
    from ikip_common.db.models import Workspace

    governance.authorize(principal, "workspace.create")
    with _session() as session:
        workspace = Workspace(tenant_id=principal.tenant_id, name=data.name)
        session.add(workspace)
        session.commit()
        result = WorkspaceOut.model_validate(workspace, from_attributes=True)
    governance.record(
        principal, "workspace.create", resource_type="workspace", resource_id=result.id
    )
    return result


@router.put("/workspaces/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(
    workspace_id: uuid.UUID,
    data: WorkspaceWrite,
    principal: ManagerPrincipal,
    governance: Governance,
) -> WorkspaceOut:
    from ikip_common.db.models import Workspace
    from sqlalchemy import select

    governance.authorize(principal, "workspace.update")
    with _session() as session:
        workspace = session.execute(
            select(Workspace).where(
                Workspace.id == workspace_id, Workspace.tenant_id == principal.tenant_id
            )
        ).scalar_one_or_none()
        if workspace is None:
            raise _missing()
        workspace.name = data.name
        session.commit()
        result = WorkspaceOut.model_validate(workspace, from_attributes=True)
    governance.record(
        principal, "workspace.update", resource_type="workspace", resource_id=workspace_id
    )
    return result


@router.delete("/workspaces/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    workspace_id: uuid.UUID, principal: ManagerPrincipal, governance: Governance
) -> Response:
    from ikip_common.db.models import Workspace
    from sqlalchemy import delete

    governance.authorize(principal, "workspace.delete")
    with _session() as session:
        result = session.execute(
            delete(Workspace).where(
                Workspace.id == workspace_id, Workspace.tenant_id == principal.tenant_id
            )
        )
        if result.rowcount == 0:
            raise _missing()
        session.commit()
    governance.record(
        principal, "workspace.delete", resource_type="workspace", resource_id=workspace_id
    )
    return Response(status_code=204)


@router.put("/workspaces/{workspace_id}/members", status_code=status.HTTP_204_NO_CONTENT)
def put_membership(
    workspace_id: uuid.UUID,
    data: MembershipWrite,
    principal: ManagerPrincipal,
    governance: Governance,
) -> Response:
    from ikip_common.db.models import AppUser, Workspace, WorkspaceMembership
    from sqlalchemy import select

    governance.authorize(principal, "workspace.membership.update")
    with _session() as session:
        workspace = session.execute(
            select(Workspace.id).where(
                Workspace.id == workspace_id, Workspace.tenant_id == principal.tenant_id
            )
        ).scalar_one_or_none()
        user = session.execute(
            select(AppUser.id).where(
                AppUser.id == data.user_id, AppUser.tenant_id == principal.tenant_id
            )
        ).scalar_one_or_none()
        if workspace is None or user is None:
            raise _missing()
        membership = session.get(WorkspaceMembership, (workspace_id, data.user_id))
        if membership is None:
            membership = WorkspaceMembership(
                workspace_id=workspace_id, user_id=data.user_id, role=data.role
            )
            session.add(membership)
        else:
            membership.role = data.role
        session.commit()
    governance.record(
        principal,
        "workspace.membership.update",
        resource_type="workspace",
        resource_id=workspace_id,
        metadata={"user_id": str(data.user_id), "role": data.role.value},
    )
    return Response(status_code=204)


@router.post(
    "/documents/{document_id}/permissions",
    status_code=status.HTTP_201_CREATED,
)
def grant_document_permission(
    document_id: uuid.UUID,
    data: PermissionWrite,
    principal: ManagerPrincipal,
    governance: Governance,
) -> dict[str, str]:
    from ikip_common.db.models import AppUser, Document, DocumentPermission, Workspace
    from sqlalchemy import select

    governance.authorize(principal, "document.permission.grant")
    with _session() as session:
        document = session.execute(
            select(Document.id).where(
                Document.id == document_id, Document.tenant_id == principal.tenant_id
            )
        ).scalar_one_or_none()
        subject_model, subject_id = (
            (AppUser, data.user_id) if data.user_id else (Workspace, data.workspace_id)
        )
        subject = session.execute(
            select(subject_model.id).where(
                subject_model.id == subject_id,
                subject_model.tenant_id == principal.tenant_id,
            )
        ).scalar_one_or_none()
        if document is None or subject is None:
            raise _missing()
        permission = DocumentPermission(
            tenant_id=principal.tenant_id,
            document_id=document_id,
            user_id=data.user_id,
            workspace_id=data.workspace_id,
        )
        session.add(permission)
        session.commit()
        permission_id = permission.id
    governance.record(
        principal,
        "document.permission.grant",
        resource_type="document",
        resource_id=document_id,
        metadata=data.model_dump(mode="json", exclude_none=True),
    )
    return {"id": str(permission_id)}


@router.get("/documents/{document_id}/permissions", response_model=list[PermissionOut])
def list_document_permissions(
    document_id: uuid.UUID, principal: ManagerPrincipal
) -> list[PermissionOut]:
    from ikip_common.db.models import Document, DocumentPermission
    from sqlalchemy import select

    with _session() as session:
        rows = session.execute(
            select(DocumentPermission)
            .join(Document, DocumentPermission.document_id == Document.id)
            .where(
                DocumentPermission.document_id == document_id,
                Document.tenant_id == principal.tenant_id,
            )
        ).scalars()
        return [PermissionOut.model_validate(row, from_attributes=True) for row in rows]


@router.delete(
    "/documents/{document_id}/permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_document_permission(
    document_id: uuid.UUID,
    permission_id: uuid.UUID,
    principal: ManagerPrincipal,
    governance: Governance,
) -> Response:
    from ikip_common.db.models import DocumentPermission
    from sqlalchemy import delete

    governance.authorize(principal, "document.permission.revoke")
    with _session() as session:
        result = session.execute(
            delete(DocumentPermission).where(
                DocumentPermission.id == permission_id,
                DocumentPermission.document_id == document_id,
                DocumentPermission.tenant_id == principal.tenant_id,
            )
        )
        if result.rowcount == 0:
            raise _missing()
        session.commit()
    governance.record(
        principal,
        "document.permission.revoke",
        resource_type="document",
        resource_id=document_id,
        metadata={"permission_id": str(permission_id)},
    )
    return Response(status_code=204)
