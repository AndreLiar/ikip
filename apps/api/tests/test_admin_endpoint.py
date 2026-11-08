"""Administration RBAC and ACL input contract tests (Story 4.7)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from ikip_common.db.models import UserRole

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
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    from ikip_common.config import get_settings

    get_settings.cache_clear()


def _client() -> TestClient:
    from ikip_api.main import create_app

    return TestClient(create_app())


def _token(client: TestClient, role: UserRole) -> str:
    return client.post(
        "/api/v1/auth/dev-token",
        json={"tenant_id": str(uuid.uuid4()), "role": role.value},
    ).json()["access_token"]


def test_admin_surface_requires_auth() -> None:
    assert _client().get("/api/v1/admin/users").status_code == 401


def test_technician_cannot_manage_users_or_workspaces() -> None:
    client = _client()
    headers = {"Authorization": f"Bearer {_token(client, UserRole.technician)}"}
    assert client.get("/api/v1/admin/users", headers=headers).status_code == 403
    assert client.get("/api/v1/admin/workspaces", headers=headers).status_code == 403


def test_permission_requires_exactly_one_subject() -> None:
    from ikip_api.admin import PermissionWrite

    with pytest.raises(ValueError):
        PermissionWrite()
    with pytest.raises(ValueError):
        PermissionWrite(user_id=uuid.uuid4(), workspace_id=uuid.uuid4())
    assert PermissionWrite(user_id=uuid.uuid4()).workspace_id is None
