"""Auth primitives (Story 1.6) — pure, framework-agnostic, testable.

A `Principal` is who the request acts as: a user, in a tenant, with a role. It is
carried in a JWT (dev: HS256 signed with `JWT_SECRET`; prod: Microsoft Entra ID /
OIDC tokens validated instead). Role checks use a hierarchy admin > manager >
technician. FastAPI wiring (dependencies) lives in `apps/api/auth.py`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from ikip_common.db.models import UserRole

# Higher number = more privilege. `require` checks use >= on this order.
_ROLE_ORDER: dict[UserRole, int] = {
    UserRole.technician: 0,
    UserRole.manager: 1,
    UserRole.admin: 2,
}

_ALGORITHM = "HS256"


class AuthError(Exception):
    """Raised when a token is missing, invalid, or expired."""


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: UserRole

    def has_role(self, required: UserRole) -> bool:
        """True if this principal's role is at least `required` in the hierarchy."""
        return _ROLE_ORDER[self.role] >= _ROLE_ORDER[required]


def encode_token(principal: Principal, secret: str, *, expires_minutes: int = 60) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(principal.user_id),
        "tenant_id": str(principal.tenant_id),
        "role": principal.role.value,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def decode_token(token: str, secret: str) -> Principal:
    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as e:  # expired, bad signature, malformed, …
        raise AuthError(str(e)) from e
    try:
        return Principal(
            user_id=uuid.UUID(payload["sub"]),
            tenant_id=uuid.UUID(payload["tenant_id"]),
            role=UserRole(payload["role"]),
        )
    except (KeyError, ValueError) as e:
        raise AuthError(f"malformed token claims: {e}") from e
