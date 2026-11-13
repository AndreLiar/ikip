"""Adversarial tenant-isolation + authz security tests (Story 6.2) — hermetic, REQUIRED.

These run in the fast `validate` CI gate (no DB, no network) and are the required
"zero cross-tenant disclosure" gate at the API layer (AC3):
  - authz-before-retrieval / -source-access: every data endpoint rejects an unauthenticated
    caller (AC2);
  - the tenant is bound from the authenticated Principal, never from the request — a caller
    CANNOT smuggle another tenant's id into the body (AC1).
The SQL-layer proof (cross-tenant + object-level ACL on chunks/sources) lives in the
DB-gated `packages/common/tests/test_security_isolation_db.py` (runs on the ephemeral Neon
branch in `db-tests`).
"""

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
    from ikip_api.governance import get_governance_service
    from ikip_api.main import create_app

    app = create_app()
    app.dependency_overrides[get_governance_service] = lambda: _FakeGov()
    return app


class _FakeGov:
    def authorize(self, principal, operation):
        return None

    def record(self, principal, operation, **kwargs):
        return None


def _token(client: TestClient, tenant_id: uuid.UUID, role: UserRole = UserRole.technician) -> str:
    body = {"tenant_id": str(tenant_id), "role": role.value}
    return client.post("/api/v1/auth/dev-token", json=body).json()["access_token"]


# --- authz-before-retrieval / -source-access (AC2) -------------------------


def test_data_endpoints_require_auth() -> None:
    client = TestClient(_app())
    assert client.post("/api/v1/retrieve", json={"query": "E42"}).status_code == 401
    assert client.post("/api/v1/ask", json={"query": "E42"}).status_code == 401
    assert client.get(f"/api/v1/documents/{uuid.uuid4()}/source-url").status_code == 401


# --- tenant is bound from the principal, not the request (AC1) --------------


def test_retrieve_binds_principal_tenant_not_request_body() -> None:
    from ikip_api.retrieval import RetrieveResponse, get_retrieve_service

    captured = {}

    def fake(*, tenant_id, **_):
        captured["tenant_id"] = tenant_id
        return RetrieveResponse(abstained=True, results=[])

    app = _app()
    app.dependency_overrides[get_retrieve_service] = lambda: fake
    client = TestClient(app)
    my_tenant = uuid.uuid4()
    attacker_tenant = uuid.uuid4()
    token = _token(client, my_tenant)

    # try to smuggle another tenant's id in the body — it must be ignored
    resp = client.post(
        "/api/v1/retrieve",
        json={"query": "E42", "tenant_id": str(attacker_tenant)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert captured["tenant_id"] == my_tenant  # bound from the JWT, never the body
    assert captured["tenant_id"] != attacker_tenant


def test_ask_binds_principal_tenant_not_request_body() -> None:
    from ikip_api.conversations import get_conversation_service
    from ikip_api.observability import get_metrics, get_telemetry, get_trace_recorder
    from ikip_api.retrieval import AskResponse, get_ask_service
    from ikip_common.telemetry import FakeTelemetry
    from ikip_common.telemetry.metrics import FakeMetrics

    captured = {}

    def fake_ask(*, tenant_id, **_):
        captured["tenant_id"] = tenant_id
        return AskResponse(
            status="abstained",
            answer=None,
            claims=[],
            warnings=[],
            abstention_reason="x",
            not_certified_notice="n",
            cache_hit=False,
        )

    class _Rec:
        def record(self, **kwargs):
            return None

    app = _app()
    app.dependency_overrides[get_ask_service] = lambda: fake_ask
    app.dependency_overrides[get_conversation_service] = lambda: _Convs()
    app.dependency_overrides[get_telemetry] = lambda: FakeTelemetry()
    app.dependency_overrides[get_trace_recorder] = lambda: _Rec()
    app.dependency_overrides[get_metrics] = lambda: FakeMetrics()
    client = TestClient(app)
    my_tenant = uuid.uuid4()
    token = _token(client, my_tenant)

    resp = client.post(
        "/api/v1/ask",
        json={"query": "E42", "tenant_id": str(uuid.uuid4())},  # smuggled -> ignored
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert captured["tenant_id"] == my_tenant


def test_two_tenants_get_distinct_bound_tenants() -> None:
    from ikip_api.retrieval import RetrieveResponse, get_retrieve_service

    seen = []

    def fake(*, tenant_id, **_):
        seen.append(tenant_id)
        return RetrieveResponse(abstained=True, results=[])

    app = _app()
    app.dependency_overrides[get_retrieve_service] = lambda: fake
    client = TestClient(app)
    a, b = uuid.uuid4(), uuid.uuid4()
    for t in (a, b):
        client.post(
            "/api/v1/retrieve",
            json={"query": "x"},
            headers={"Authorization": f"Bearer {_token(client, t)}"},
        )
    assert seen == [a, b]  # each request is bound to its own JWT's tenant


class _Convs:
    def create(self, *, tenant_id, user_id, title):
        from datetime import UTC, datetime

        from ikip_api.conversations import ConversationOut

        return ConversationOut(id="c1", title=title, created_at=datetime.now(UTC))

    def add_message(self, *, tenant_id, user_id, conversation_id, role, content, answer_payload):
        from datetime import UTC, datetime

        from ikip_api.conversations import MessageOut

        return MessageOut(
            id="m1",
            role=role,
            content=content,
            answer_payload=answer_payload,
            created_at=datetime.now(UTC),
        )
