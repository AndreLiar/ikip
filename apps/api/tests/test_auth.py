"""Auth + RBAC tests (Story 1.6 AC4). Hermetic: no DB, no live services.

The env values below are dummy placeholders — these tests never connect to any
backend; they only need Settings() to validate. JWT + RBAC logic is pure.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from ikip_common.auth import AuthError, Principal, decode_token, encode_token
from ikip_common.db.models import UserRole

_S = "unit-test-signing-secret-0123456789abcdef"  # >=32 chars for HS256

_ENV = {
    "DATABASE_URL": "postgresql://u:p@host/db",
    "R2_ACCOUNT_ID": "acct",
    "R2_ENDPOINT": "https://acct.r2.cloudflarestorage.com",
    "R2_BUCKET": "ikip-test",
    "R2_ACCESS_KEY_ID": "ak",
    "R2_SECRET_ACCESS_KEY": "sk",
    "REDIS_URL": "redis://localhost:6379/0",
    "JWT_SECRET": "unit-test-secret-0123456789abcdef0123",
    "AUTH_DEV_LOGIN": "true",
}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _ENV.items():
        monkeypatch.setenv(k, v)
    from ikip_common.config import get_settings

    get_settings.cache_clear()


# ---- unit: token + role hierarchy ---------------------------------------


def test_token_round_trip() -> None:
    p = Principal(uuid.uuid4(), uuid.uuid4(), UserRole.manager)
    token = encode_token(p, _S, expires_minutes=5)
    assert decode_token(token, _S) == p


def test_bad_signature_rejected() -> None:
    token = encode_token(Principal(uuid.uuid4(), uuid.uuid4(), UserRole.admin), _S)
    with pytest.raises(AuthError):
        decode_token(token, _S + "x")


def test_expired_rejected() -> None:
    token = encode_token(
        Principal(uuid.uuid4(), uuid.uuid4(), UserRole.technician), _S, expires_minutes=-1
    )
    with pytest.raises(AuthError):
        decode_token(token, _S)


def test_role_hierarchy() -> None:
    admin = Principal(uuid.uuid4(), uuid.uuid4(), UserRole.admin)
    tech = Principal(uuid.uuid4(), uuid.uuid4(), UserRole.technician)
    assert admin.has_role(UserRole.admin) and admin.has_role(UserRole.technician)
    assert tech.has_role(UserRole.technician)
    assert not tech.has_role(UserRole.admin)


# ---- integration: endpoints via TestClient ------------------------------


def _client() -> TestClient:
    from ikip_api.main import create_app

    return TestClient(create_app())


def _token(role: UserRole, tenant_id: uuid.UUID | None = None) -> str:
    body = {"tenant_id": str(tenant_id or uuid.uuid4()), "role": role.value}
    return _client().post("/api/v1/auth/dev-token", json=body).json()["access_token"]


def test_me_requires_auth() -> None:
    assert _client().get("/api/v1/me").status_code == 401


def test_me_with_token_returns_principal() -> None:
    tenant = uuid.uuid4()
    token = _token(UserRole.technician, tenant)
    resp = _client().get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == str(tenant)  # tenant binding carried
    assert resp.json()["role"] == "technician"


def test_admin_endpoint_forbids_technician() -> None:
    token = _token(UserRole.technician)
    resp = _client().get("/api/v1/admin/ping", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_admin_endpoint_allows_admin() -> None:
    token = _token(UserRole.admin)
    resp = _client().get("/api/v1/admin/ping", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"pong": "admin"}


def test_invalid_token_rejected() -> None:
    resp = _client().get("/api/v1/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
