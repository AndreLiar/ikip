"""Document management endpoints (Story 4.2). Hermetic: no DB, no R2, no network."""

import uuid
from datetime import UTC, datetime

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
    from ikip_api.governance import get_governance_service
    from ikip_api.main import create_app

    app = create_app()
    app.dependency_overrides[get_governance_service] = lambda: _FakeGovernance()
    return app


class _FakeGovernance:
    def authorize(self, principal, operation):
        return None

    def record(self, principal, operation, **kwargs):
        return None


def _token(client: TestClient, tenant: uuid.UUID, role: UserRole = UserRole.technician) -> str:
    return client.post(
        "/api/v1/auth/dev-token", json={"tenant_id": str(tenant), "role": role.value}
    ).json()["access_token"]


class _FakeLibrary:
    def __init__(self) -> None:
        self.uploads: list[dict] = []

    def list_documents(self, *, tenant_id, query, document_type, equipment_id):
        from ikip_api.library import DocumentSummary

        return [
            DocumentSummary(
                id="d1",
                title="Pump Manual",
                type="manual",
                current_revision="B",
                version_count=2,
                created_at=datetime.now(UTC),
            )
        ]

    def list_versions(self, *, tenant_id, document_id):
        from ikip_api.library import DocumentNotFoundError, VersionInfo

        if str(document_id) == "00000000-0000-0000-0000-000000000000":
            raise DocumentNotFoundError("nope")
        return [
            VersionInfo(
                id="v1",
                revision="B",
                is_current=True,
                checksum="abc",
                publication_date=None,
                effective_date=None,
                created_at=datetime.now(UTC),
            )
        ]

    def upload(self, *, tenant_id, filename, content, content_type):
        from ikip_api.library import UploadResponse

        self.uploads.append({"filename": filename, "len": len(content), "ct": content_type})
        return UploadResponse(job_id="j1", state="pending", source=f"upload://{filename}")

    def update_document_type(self, *, tenant_id, document_id, document_type):
        from ikip_api.library import DocumentSummary

        return DocumentSummary(
            id=str(document_id),
            title="Pump Manual",
            type=document_type,
            current_revision="B",
            version_count=2,
            created_at=datetime.now(UTC),
        )

    def list_jobs(self, *, tenant_id, limit):
        from ikip_api.library import JobInfo

        return [
            JobInfo(
                id="j1",
                source="upload://x.pdf",
                state="pending",
                attempts=0,
                created_at=datetime.now(UTC),
            )
        ]


def _client_with_fake(fake):
    from ikip_api.library import get_library_service

    app = _app()
    app.dependency_overrides[get_library_service] = lambda: fake
    return TestClient(app)


def test_list_documents_requires_auth() -> None:
    assert TestClient(_app()).get("/api/v1/documents").status_code == 401


def test_list_documents() -> None:
    client = _client_with_fake(_FakeLibrary())
    token = _token(client, uuid.uuid4())
    resp = client.get(
        "/api/v1/documents?query=pump&type=manual",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()[0]["current_revision"] == "B"
    assert resp.json()[0]["version_count"] == 2


def test_list_versions_and_404() -> None:
    client = _client_with_fake(_FakeLibrary())
    token = _token(client, uuid.uuid4())
    ok = client.get(
        f"/api/v1/documents/{uuid.uuid4()}/versions", headers={"Authorization": f"Bearer {token}"}
    )
    assert ok.status_code == 200 and ok.json()[0]["is_current"] is True
    missing = client.get(
        "/api/v1/documents/00000000-0000-0000-0000-000000000000/versions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert missing.status_code == 404


def test_manager_can_categorize_document() -> None:
    client = _client_with_fake(_FakeLibrary())
    document_id = uuid.uuid4()
    manager = _token(client, uuid.uuid4(), UserRole.manager)
    response = client.patch(
        f"/api/v1/documents/{document_id}",
        headers={"Authorization": f"Bearer {manager}"},
        json={"type": "maintenance-manual"},
    )
    assert response.status_code == 200
    assert response.json()["type"] == "maintenance-manual"


def test_upload_requires_manager_role() -> None:
    fake = _FakeLibrary()
    client = _client_with_fake(fake)
    tech = _token(client, uuid.uuid4(), UserRole.technician)
    resp = client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {tech}"},
        files={"file": ("x.pdf", b"%PDF-data", "application/pdf")},
    )
    assert resp.status_code == 403  # technician can't upload (write = manager+)
    assert fake.uploads == []


def test_upload_creates_job_as_manager() -> None:
    fake = _FakeLibrary()
    client = _client_with_fake(fake)
    mgr = _token(client, uuid.uuid4(), UserRole.manager)
    resp = client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {mgr}"},
        files={"file": ("manual.pdf", b"%PDF-1.7 bytes", "application/pdf")},
    )
    assert resp.status_code == 202
    assert resp.json()["state"] == "pending"
    assert (
        fake.uploads[0]["filename"] == "manual.pdf" and fake.uploads[0]["ct"] == "application/pdf"
    )


def test_upload_rejects_empty_file() -> None:
    fake = _FakeLibrary()
    client = _client_with_fake(fake)
    mgr = _token(client, uuid.uuid4(), UserRole.manager)
    resp = client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {mgr}"},
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert resp.status_code == 400
    assert fake.uploads == []


def test_list_jobs() -> None:
    client = _client_with_fake(_FakeLibrary())
    token = _token(client, uuid.uuid4(), UserRole.manager)
    resp = client.get("/api/v1/ingestion-jobs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200 and resp.json()[0]["state"] == "pending"


def test_list_jobs_requires_manager() -> None:
    client = _client_with_fake(_FakeLibrary())
    token = _token(client, uuid.uuid4(), UserRole.technician)
    resp = client.get("/api/v1/ingestion-jobs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
