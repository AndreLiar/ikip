"""Cross-tenant organization lifecycle authorization contract."""

import uuid

import pytest
from fastapi.testclient import TestClient
from ikip_common.db.models import UserRole

_OPERATOR_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
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
    "PLATFORM_OPERATOR_USER_IDS": str(_OPERATOR_ID),
}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    from ikip_common.config import get_settings

    get_settings.cache_clear()


def _client() -> TestClient:
    from ikip_api.main import create_app

    return TestClient(create_app())


def _token(client: TestClient, user_id: uuid.UUID) -> str:
    response = client.post(
        "/api/v1/auth/dev-token",
        json={
            "user_id": str(user_id),
            "tenant_id": str(uuid.uuid4()),
            "role": UserRole.admin.value,
        },
    )
    return response.json()["access_token"]


def test_platform_surface_requires_authentication() -> None:
    assert _client().get("/api/v1/platform/organizations").status_code == 401


def test_tenant_admin_is_not_implicitly_a_platform_operator() -> None:
    client = _client()
    token = _token(client, uuid.uuid4())

    response = client.get(
        "/api/v1/platform/organizations",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "requires platform operator capability"


def test_destructive_delete_requires_both_confirmations_before_database_access() -> None:
    client = _client()
    token = _token(client, _OPERATOR_ID)
    headers = {"Authorization": f"Bearer {token}"}
    path = f"/api/v1/platform/organizations/{uuid.uuid4()}"

    assert client.delete(path, headers=headers).status_code == 400
    assert client.delete(f"{path}?confirm=true", headers=headers).status_code == 400


def test_create_contract_rejects_invalid_admin_email_before_database_access() -> None:
    client = _client()
    token = _token(client, _OPERATOR_ID)

    response = client.post(
        "/api/v1/platform/organizations",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Factory A", "admin_email": "invalid"},
    )

    assert response.status_code == 422
