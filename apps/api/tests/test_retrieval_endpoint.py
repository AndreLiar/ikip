"""Retrieval + ask endpoint tests (Epic 3 wiring). Hermetic: no DB, no network.

The heavy services (hybrid retrieval, grounded answer) are injected as FastAPI
dependencies and overridden here with fakes — so these assert the HTTP contract,
auth + tenant binding, and citation mapping, without langchain/Azure/Postgres.
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
    app.dependency_overrides[get_governance_service] = lambda: _FakeGovernance()
    return app


class _FakeGovernance:
    def authorize(self, principal, operation):
        return None

    def record(self, principal, operation, **kwargs):
        return None


def _token(client: TestClient, tenant_id: uuid.UUID, role: UserRole = UserRole.technician) -> str:
    body = {"tenant_id": str(tenant_id), "role": role.value}
    return client.post("/api/v1/auth/dev-token", json=body).json()["access_token"]


# --- /retrieve -------------------------------------------------------------


def test_retrieve_requires_auth() -> None:
    client = TestClient(_app())
    assert client.post("/api/v1/retrieve", json={"query": "E42"}).status_code == 401


def test_retrieve_returns_results_with_citations() -> None:
    from ikip_api.retrieval import (
        Citation,
        RetrievedChunk,
        RetrieveResponse,
        get_retrieve_service,
    )

    captured = {}

    def fake_service(
        *, tenant_id, query, k, mode, current_only, document_type, equipment_id, user_id
    ):
        captured.update(tenant_id=tenant_id, query=query, k=k, mode=mode, current_only=current_only)
        return RetrieveResponse(
            abstained=False,
            results=[
                RetrievedChunk(
                    content="Fault E42: pump overheat.",
                    citation=Citation(
                        revision="A", hierarchy_path="3.2", page_start=142, score=0.9
                    ),
                )
            ],
        )

    app = _app()
    app.dependency_overrides[get_retrieve_service] = lambda: fake_service
    client = TestClient(app)
    tenant = uuid.uuid4()
    token = _token(client, tenant)

    resp = client.post(
        "/api/v1/retrieve",
        json={"query": "E42", "k": 3, "current_only": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["abstained"] is False
    assert body["results"][0]["citation"]["revision"] == "A"
    assert body["results"][0]["citation"]["page_start"] == 142
    # the endpoint bound the query to the authenticated tenant (FR21/NFR10)
    assert captured["tenant_id"] == tenant and captured["k"] == 3
    assert captured["mode"] == "hybrid"  # default mode


def test_retrieve_accepts_search_mode() -> None:
    from ikip_api.retrieval import RetrieveResponse, get_retrieve_service

    seen = {}

    def fake_service(*, mode, **_):
        seen["mode"] = mode
        return RetrieveResponse(abstained=True, results=[])

    app = _app()
    app.dependency_overrides[get_retrieve_service] = lambda: fake_service
    client = TestClient(app)
    token = _token(client, uuid.uuid4())
    for mode in ("lexical", "vector", "hybrid"):
        client.post(
            "/api/v1/retrieve",
            json={"query": "E42", "mode": mode},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert seen["mode"] == mode
    # invalid mode rejected by schema
    bad = client.post(
        "/api/v1/retrieve",
        json={"query": "x", "mode": "fuzzy"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bad.status_code == 422


def test_retrieve_surfaces_abstention() -> None:
    from ikip_api.retrieval import RetrieveResponse, get_retrieve_service

    app = _app()
    app.dependency_overrides[get_retrieve_service] = lambda: (
        lambda **_: RetrieveResponse(abstained=True, results=[])
    )
    client = TestClient(app)
    token = _token(client, uuid.uuid4())
    resp = client.post(
        "/api/v1/retrieve", json={"query": "nope"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200 and resp.json() == {"abstained": True, "results": []}


def test_retrieve_validates_query() -> None:
    client = TestClient(_app())
    token = _token(client, uuid.uuid4())
    resp = client.post(
        "/api/v1/retrieve", json={"query": ""}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 422  # empty query rejected by schema


# --- /ask ------------------------------------------------------------------


def test_ask_returns_grounded_answer() -> None:
    from ikip_api.retrieval import (
        AnsweredClaimOut,
        AskResponse,
        Citation,
        get_ask_service,
    )

    def fake_ask(*, tenant_id, query, equipment_model, revision, user_id):
        return AskResponse(
            status="answered",
            answer="E42 = pump overheat. [E1]",
            claims=[
                AnsweredClaimOut(
                    text="E42 = pump overheat.",
                    safety_critical=False,
                    citations=[Citation(revision="A", hierarchy_path="3.2")],
                )
            ],
            warnings=[],
            abstention_reason=None,
            not_certified_notice="not certified",
            cache_hit=False,
        )

    app = _app()
    app.dependency_overrides[get_ask_service] = lambda: fake_ask
    client = TestClient(app)
    token = _token(client, uuid.uuid4())
    resp = client.post(
        "/api/v1/ask", json={"query": "What is E42?"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "answered"
    assert body["claims"][0]["citations"][0]["revision"] == "A"
    assert body["not_certified_notice"]  # always present (AC5)
