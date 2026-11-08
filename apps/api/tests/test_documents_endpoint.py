"""Source-url endpoint tests (Story 4.5 partial). Hermetic: no DB, no R2, no network."""

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
    for k, v in _ENV.items():
        monkeypatch.setenv(k, v)
    from ikip_common.config import get_settings

    get_settings.cache_clear()


def _app():
    from ikip_api.main import create_app

    return create_app()


def _token(client: TestClient, tenant_id: uuid.UUID, role: UserRole = UserRole.technician) -> str:
    body = {"tenant_id": str(tenant_id), "role": role.value}
    return client.post("/api/v1/auth/dev-token", json=body).json()["access_token"]


def test_source_url_requires_auth() -> None:
    client = TestClient(_app())
    assert client.get(f"/api/v1/documents/{uuid.uuid4()}/source-url").status_code == 401


def test_source_url_presigns_after_authorize() -> None:
    from ikip_api.documents import SourceUrlResponse, get_source_url_service

    seen = {}

    def fake(*, tenant_id, user_id, version_id, expires_s):
        seen.update(tenant_id=tenant_id, version_id=version_id)
        return SourceUrlResponse(url="https://r2.example/presigned?sig=x", expires_s=expires_s)

    app = _app()
    app.dependency_overrides[get_source_url_service] = lambda: fake
    client = TestClient(app)
    tenant = uuid.uuid4()
    vid = uuid.uuid4()
    token = _token(client, tenant)
    resp = client.get(
        f"/api/v1/documents/{vid}/source-url", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["url"].startswith("https://r2.example/")
    # the request was bound to the authenticated tenant (FR21/NFR10)
    assert seen["tenant_id"] == tenant and seen["version_id"] == vid


def test_source_url_404_when_not_in_tenant() -> None:
    from ikip_api.documents import SourceNotFoundError, get_source_url_service

    def fake(**_):
        raise SourceNotFoundError("nope")

    app = _app()
    app.dependency_overrides[get_source_url_service] = lambda: fake
    client = TestClient(app)
    token = _token(client, uuid.uuid4())
    resp = client.get(
        f"/api/v1/documents/{uuid.uuid4()}/source-url",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
