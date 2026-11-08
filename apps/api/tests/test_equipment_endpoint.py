"""Equipment catalog contract and RBAC tests (Story 4.3)."""

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


class _FakeEquipment:
    def __init__(self) -> None:
        self.associations: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]] = []

    @staticmethod
    def _item(data=None):
        from ikip_api.equipment import EquipmentOut

        values = data.model_dump() if data else {}
        return EquipmentOut(
            id=uuid.UUID("10000000-0000-0000-0000-000000000001"),
            manufacturer=values.get("manufacturer", "Siemens"),
            model=values.get("model", "S7-1500"),
            revision=values.get("revision", "A"),
            asset_id=values.get("asset_id", "LINE-1"),
        )

    def list(self, *, tenant_id, query):
        return [self._item()]

    def create(self, *, tenant_id, data):
        return self._item(data)

    def update(self, *, tenant_id, equipment_id, data):
        return self._item(data)

    def delete(self, *, tenant_id, equipment_id):
        return None

    def associate(self, *, tenant_id, equipment_id, document_id):
        self.associations.append((tenant_id, equipment_id, document_id))

    def dissociate(self, *, tenant_id, equipment_id, document_id):
        return None


def _client(fake: _FakeEquipment) -> TestClient:
    from ikip_api.equipment import get_equipment_service
    from ikip_api.governance import get_governance_service
    from ikip_api.main import create_app

    app = create_app()
    app.dependency_overrides[get_equipment_service] = lambda: fake
    app.dependency_overrides[get_governance_service] = lambda: _FakeGovernance()
    return TestClient(app)


class _FakeGovernance:
    def authorize(self, principal, operation):
        return None

    def record(self, principal, operation, **kwargs):
        return None


def _token(client: TestClient, tenant: uuid.UUID, role: UserRole) -> str:
    return client.post(
        "/api/v1/auth/dev-token", json={"tenant_id": str(tenant), "role": role.value}
    ).json()["access_token"]


def test_catalog_read_requires_auth() -> None:
    assert _client(_FakeEquipment()).get("/api/v1/equipment").status_code == 401


def test_technician_can_browse_but_not_create() -> None:
    client = _client(_FakeEquipment())
    token = _token(client, uuid.uuid4(), UserRole.technician)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/equipment?query=S7", headers=headers).status_code == 200
    response = client.post(
        "/api/v1/equipment",
        headers=headers,
        json={"manufacturer": "Siemens", "model": "S7-1500"},
    )
    assert response.status_code == 403


def test_manager_crud_and_document_association_are_tenant_bound() -> None:
    tenant = uuid.uuid4()
    equipment_id = uuid.uuid4()
    document_id = uuid.uuid4()
    fake = _FakeEquipment()
    client = _client(fake)
    headers = {"Authorization": f"Bearer {_token(client, tenant, UserRole.manager)}"}
    created = client.post(
        "/api/v1/equipment",
        headers=headers,
        json={"manufacturer": "ABB", "model": "ACS880", "revision": "2"},
    )
    assert created.status_code == 201 and created.json()["model"] == "ACS880"
    associated = client.put(
        f"/api/v1/equipment/{equipment_id}/documents/{document_id}", headers=headers
    )
    assert associated.status_code == 204
    assert fake.associations == [(tenant, equipment_id, document_id)]
