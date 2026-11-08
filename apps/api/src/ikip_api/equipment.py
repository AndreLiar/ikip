"""Tenant-scoped equipment catalog and document associations (Story 4.3)."""

from __future__ import annotations

import uuid
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from ikip_common.auth import Principal
from ikip_common.db.models import UserRole
from pydantic import BaseModel, Field

from ikip_api.auth import CurrentPrincipal, require_role

router = APIRouter(prefix="/equipment", tags=["equipment"])


class EquipmentWrite(BaseModel):
    manufacturer: str = Field(min_length=1, max_length=255)
    model: str = Field(min_length=1, max_length=255)
    revision: str | None = Field(default=None, max_length=64)
    asset_id: str | None = Field(default=None, max_length=255)


class EquipmentOut(EquipmentWrite):
    id: uuid.UUID


class CatalogNotFoundError(Exception):
    pass


class EquipmentService(Protocol):
    def list(self, *, tenant_id: uuid.UUID, query: str | None) -> list[EquipmentOut]: ...
    def create(self, *, tenant_id: uuid.UUID, data: EquipmentWrite) -> EquipmentOut: ...
    def update(
        self, *, tenant_id: uuid.UUID, equipment_id: uuid.UUID, data: EquipmentWrite
    ) -> EquipmentOut: ...
    def delete(self, *, tenant_id: uuid.UUID, equipment_id: uuid.UUID) -> None: ...
    def associate(
        self, *, tenant_id: uuid.UUID, equipment_id: uuid.UUID, document_id: uuid.UUID
    ) -> None: ...
    def dissociate(
        self, *, tenant_id: uuid.UUID, equipment_id: uuid.UUID, document_id: uuid.UUID
    ) -> None: ...


class _DbEquipmentService:
    @staticmethod
    def _out(equipment) -> EquipmentOut:  # noqa: ANN001
        return EquipmentOut(
            id=equipment.id,
            manufacturer=equipment.manufacturer,
            model=equipment.model,
            revision=equipment.revision,
            asset_id=equipment.asset_id,
        )

    def list(self, *, tenant_id: uuid.UUID, query: str | None) -> list[EquipmentOut]:
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import Equipment
        from sqlalchemy import or_, select

        statement = select(Equipment).where(Equipment.tenant_id == tenant_id)
        if query:
            pattern = f"%{query}%"
            statement = statement.where(
                or_(
                    Equipment.manufacturer.ilike(pattern),
                    Equipment.model.ilike(pattern),
                    Equipment.asset_id.ilike(pattern),
                )
            )
        with make_session_factory()() as session:
            rows = session.execute(statement.order_by(Equipment.manufacturer, Equipment.model))
            return [self._out(item) for item in rows.scalars()]

    def create(self, *, tenant_id: uuid.UUID, data: EquipmentWrite) -> EquipmentOut:
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import Equipment

        with make_session_factory()() as session:
            equipment = Equipment(tenant_id=tenant_id, **data.model_dump())
            session.add(equipment)
            session.commit()
            session.refresh(equipment)
            return self._out(equipment)

    def update(
        self, *, tenant_id: uuid.UUID, equipment_id: uuid.UUID, data: EquipmentWrite
    ) -> EquipmentOut:
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import Equipment
        from sqlalchemy import select

        with make_session_factory()() as session:
            equipment = session.execute(
                select(Equipment).where(
                    Equipment.id == equipment_id, Equipment.tenant_id == tenant_id
                )
            ).scalar_one_or_none()
            if equipment is None:
                raise CatalogNotFoundError
            for name, value in data.model_dump().items():
                setattr(equipment, name, value)
            session.commit()
            return self._out(equipment)

    def delete(self, *, tenant_id: uuid.UUID, equipment_id: uuid.UUID) -> None:
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import Equipment
        from sqlalchemy import delete

        with make_session_factory()() as session:
            result = session.execute(
                delete(Equipment).where(
                    Equipment.id == equipment_id, Equipment.tenant_id == tenant_id
                )
            )
            if result.rowcount == 0:
                raise CatalogNotFoundError
            session.commit()

    def associate(
        self, *, tenant_id: uuid.UUID, equipment_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import Document, DocumentEquipment, Equipment
        from sqlalchemy import select

        with make_session_factory()() as session:
            equipment = session.execute(
                select(Equipment.id).where(
                    Equipment.id == equipment_id, Equipment.tenant_id == tenant_id
                )
            ).scalar_one_or_none()
            document = session.execute(
                select(Document.id).where(
                    Document.id == document_id, Document.tenant_id == tenant_id
                )
            ).scalar_one_or_none()
            if equipment is None or document is None:
                raise CatalogNotFoundError
            existing = session.get(DocumentEquipment, (document_id, equipment_id))
            if existing is None:
                session.add(DocumentEquipment(document_id=document_id, equipment_id=equipment_id))
                session.commit()

    def dissociate(
        self, *, tenant_id: uuid.UUID, equipment_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import Document, DocumentEquipment, Equipment
        from sqlalchemy import delete, select

        with make_session_factory()() as session:
            allowed = session.execute(
                select(DocumentEquipment.document_id)
                .join(Document, DocumentEquipment.document_id == Document.id)
                .join(Equipment, DocumentEquipment.equipment_id == Equipment.id)
                .where(
                    Document.id == document_id,
                    Equipment.id == equipment_id,
                    Document.tenant_id == tenant_id,
                    Equipment.tenant_id == tenant_id,
                )
            ).scalar_one_or_none()
            if allowed is None:
                raise CatalogNotFoundError
            session.execute(
                delete(DocumentEquipment).where(
                    DocumentEquipment.document_id == document_id,
                    DocumentEquipment.equipment_id == equipment_id,
                )
            )
            session.commit()


def get_equipment_service() -> EquipmentService:
    return _DbEquipmentService()


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource not found")


@router.get("", response_model=list[EquipmentOut])
def list_equipment(
    principal: CurrentPrincipal,
    service: Annotated[EquipmentService, Depends(get_equipment_service)],
    query: Annotated[str | None, Query(max_length=200)] = None,
) -> list[EquipmentOut]:
    return service.list(tenant_id=principal.tenant_id, query=query)


@router.post("", response_model=EquipmentOut, status_code=status.HTTP_201_CREATED)
def create_equipment(
    data: EquipmentWrite,
    principal: Annotated[Principal, Depends(require_role(UserRole.manager))],
    service: Annotated[EquipmentService, Depends(get_equipment_service)],
) -> EquipmentOut:
    return service.create(tenant_id=principal.tenant_id, data=data)


@router.put("/{equipment_id}", response_model=EquipmentOut)
def update_equipment(
    equipment_id: uuid.UUID,
    data: EquipmentWrite,
    principal: Annotated[Principal, Depends(require_role(UserRole.manager))],
    service: Annotated[EquipmentService, Depends(get_equipment_service)],
) -> EquipmentOut:
    try:
        return service.update(tenant_id=principal.tenant_id, equipment_id=equipment_id, data=data)
    except CatalogNotFoundError as exc:
        raise _not_found() from exc


@router.delete("/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_equipment(
    equipment_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_role(UserRole.manager))],
    service: Annotated[EquipmentService, Depends(get_equipment_service)],
) -> Response:
    try:
        service.delete(tenant_id=principal.tenant_id, equipment_id=equipment_id)
    except CatalogNotFoundError as exc:
        raise _not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{equipment_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def associate_document(
    equipment_id: uuid.UUID,
    document_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_role(UserRole.manager))],
    service: Annotated[EquipmentService, Depends(get_equipment_service)],
) -> Response:
    try:
        service.associate(
            tenant_id=principal.tenant_id,
            equipment_id=equipment_id,
            document_id=document_id,
        )
    except CatalogNotFoundError as exc:
        raise _not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{equipment_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def dissociate_document(
    equipment_id: uuid.UUID,
    document_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_role(UserRole.manager))],
    service: Annotated[EquipmentService, Depends(get_equipment_service)],
) -> Response:
    try:
        service.dissociate(
            tenant_id=principal.tenant_id,
            equipment_id=equipment_id,
            document_id=document_id,
        )
    except CatalogNotFoundError as exc:
        raise _not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
