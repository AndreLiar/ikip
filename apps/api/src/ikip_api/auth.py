"""FastAPI auth wiring (Story 1.6).

- `CurrentPrincipal` — dependency that extracts + validates the bearer token and
  returns a `Principal` (401 on missing/invalid). Authorizes every request and
  binds it to a tenant (authorize-before-retrieve, FR21).
- `require_role(min_role)` — dependency factory for RBAC (403 if under-privileged).
- `POST /api/v1/auth/dev-token` — DEV-ONLY (guarded by AUTH_DEV_LOGIN) token minting
  for local accounts; prod replaces this with Microsoft Entra ID (OIDC) validation.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from ikip_common import get_settings
from ikip_common.auth import AuthError, Principal, decode_token, encode_token
from ikip_common.db.models import UserRole
from pydantic import BaseModel

router = APIRouter()


def get_current_principal(
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1]
    try:
        return decode_token(token, get_settings().jwt_secret.get_secret_value())
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def require_role(min_role: UserRole):
    """Dependency factory: require at least `min_role` (hierarchy-aware)."""

    def _dep(principal: CurrentPrincipal) -> Principal:
        if not principal.has_role(min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires role >= {min_role.value}",
            )
        return principal

    return _dep


def require_platform_operator(principal: CurrentPrincipal) -> Principal:
    """Authorize a cross-tenant operator by immutable IdP subject UUID."""
    configured = {
        value.strip()
        for value in get_settings().platform_operator_user_ids.split(",")
        if value.strip()
    }
    if str(principal.user_id) not in configured:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="requires platform operator capability",
        )
    return principal


# --- dev-only token issuance --------------------------------------------


class DevTokenRequest(BaseModel):
    user_id: uuid.UUID | None = None
    tenant_id: uuid.UUID
    role: UserRole = UserRole.technician


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/auth/dev-token", response_model=TokenResponse, tags=["auth"])
def dev_token(req: DevTokenRequest) -> TokenResponse:
    settings = get_settings()
    if not settings.auth_dev_login:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="dev login disabled")
    principal = Principal(
        user_id=req.user_id or uuid.uuid4(),
        tenant_id=req.tenant_id,
        role=req.role,
    )
    token = encode_token(
        principal,
        settings.jwt_secret.get_secret_value(),
        expires_minutes=settings.jwt_expire_minutes,
    )
    return TokenResponse(access_token=token)
