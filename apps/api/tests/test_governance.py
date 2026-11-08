"""Quota/rate-limit enforcement and audit completeness (Story 4.8)."""

import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from ikip_api.governance import RedisRateLimiter
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


class _Redis:
    def __init__(self, counts: list[int]) -> None:
        self.counts = iter(counts)

    def eval(self, script, keys, key, window):
        return next(self.counts)


def test_rate_limiter_returns_clear_429_with_retry_after() -> None:
    limiter = object.__new__(RedisRateLimiter)
    limiter._client = _Redis([1, 3])
    tenant = uuid.uuid4()
    assert limiter.consume(tenant_id=tenant, limit=2) == 1
    with pytest.raises(HTTPException) as exc:
        limiter.consume(tenant_id=tenant, limit=2)
    assert exc.value.status_code == 429
    assert exc.value.headers == {"Retry-After": "60"}


class _Governance:
    def __init__(self, blocked: bool = False) -> None:
        self.blocked = blocked
        self.events: list[tuple[str, dict]] = []

    def authorize(self, principal, operation):
        if self.blocked:
            raise HTTPException(status_code=429, detail=f"daily quota exceeded for {operation}")

    def record(self, principal, operation, **kwargs):
        self.events.append((operation, kwargs))


class _Library:
    def upload(self, *, tenant_id, filename, content, content_type):
        from ikip_api.library import UploadResponse

        return UploadResponse(job_id=str(uuid.uuid4()), state="pending", source=filename)


def _client(governance: _Governance) -> TestClient:
    from ikip_api.governance import get_governance_service
    from ikip_api.library import get_library_service
    from ikip_api.main import create_app

    app = create_app()
    app.dependency_overrides[get_governance_service] = lambda: governance
    app.dependency_overrides[get_library_service] = lambda: _Library()
    return TestClient(app)


def _manager_token(client: TestClient) -> str:
    return client.post(
        "/api/v1/auth/dev-token",
        json={"tenant_id": str(uuid.uuid4()), "role": UserRole.manager.value},
    ).json()["access_token"]


def test_quota_blocks_operation_before_side_effect() -> None:
    client = _client(_Governance(blocked=True))
    response = client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {_manager_token(client)}"},
        files={"file": ("manual.pdf", b"pdf", "application/pdf")},
    )
    assert response.status_code == 429
    assert "quota" in response.json()["detail"]


def test_successful_operation_records_complete_audit() -> None:
    governance = _Governance()
    client = _client(governance)
    response = client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {_manager_token(client)}"},
        files={"file": ("manual.pdf", b"pdf", "application/pdf")},
    )
    assert response.status_code == 202
    operation, data = governance.events[0]
    assert operation == "document.upload"
    assert data["resource_type"] == "ingestion_job"
    assert data["metadata"]["filename"] == "manual.pdf"
