"""Conversation history & feedback endpoints (Story 4.6). Hermetic: no DB, no network."""

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
    from ikip_api.main import create_app

    return create_app()


def _token(client: TestClient, tenant: uuid.UUID, role: UserRole = UserRole.technician) -> str:
    return client.post(
        "/api/v1/auth/dev-token", json={"tenant_id": str(tenant), "role": role.value}
    ).json()["access_token"]


class _FakeConversations:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def create(self, *, tenant_id, user_id, title):
        from ikip_api.conversations import ConversationOut

        self.calls.append(("create", tenant_id, user_id))
        return ConversationOut(id="c1", title=title, created_at=datetime.now(UTC))

    def list(self, *, tenant_id, user_id):
        from ikip_api.conversations import ConversationOut

        self.calls.append(("list", tenant_id, user_id))
        return [ConversationOut(id="c1", title="T", created_at=datetime.now(UTC))]

    def messages(self, *, tenant_id, user_id, conversation_id):
        from ikip_api.conversations import MessageOut, NotFoundError

        if str(conversation_id) == "00000000-0000-0000-0000-000000000000":
            raise NotFoundError("x")
        return [
            MessageOut(
                id="m1",
                role="assistant",
                content="A Pod is …",
                answer_payload={"status": "answered", "claims": []},
                created_at=datetime.now(UTC),
            )
        ]

    def add_message(self, *, tenant_id, user_id, conversation_id, role, content, answer_payload):
        from ikip_api.conversations import MessageOut

        self.calls.append(("add", role, bool(answer_payload)))
        return MessageOut(
            id="m1",
            role=role,
            content=content,
            answer_payload=answer_payload,
            created_at=datetime.now(UTC),
        )

    def feedback(self, *, tenant_id, user_id, message_id, rating, flagged, reason):
        from ikip_api.conversations import FeedbackOut

        self.calls.append(("feedback", rating, flagged))
        return FeedbackOut(
            id="f1",
            message_id=str(message_id),
            user_id=str(user_id),
            rating=rating,
            flagged=flagged,
            reason=reason,
            created_at=datetime.now(UTC),
        )

    def list_feedback(self, *, tenant_id, flagged_only, limit):
        from ikip_api.conversations import FeedbackOut

        self.calls.append(("list_feedback", flagged_only))
        return [
            FeedbackOut(
                id="f1",
                message_id="m1",
                user_id="u1",
                rating=-1,
                flagged=True,
                reason="wrong page",
                created_at=datetime.now(UTC),
            )
        ]


def _client(fake):
    from ikip_api.conversations import get_conversation_service

    app = _app()
    app.dependency_overrides[get_conversation_service] = lambda: fake
    return TestClient(app)


def test_requires_auth() -> None:
    assert TestClient(_app()).get("/api/v1/conversations").status_code == 401


def test_create_and_list_bound_to_user() -> None:
    fake = _FakeConversations()
    client = _client(fake)
    tenant = uuid.uuid4()
    token = _token(client, tenant)
    created = client.post(
        "/api/v1/conversations",
        json={"title": "Pumps"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 201 and created.json()["id"] == "c1"
    listed = client.get("/api/v1/conversations", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200
    # both calls were bound to the authenticated tenant (ownership, NFR10)
    assert all(c[1] == tenant for c in fake.calls)


def test_messages_persist_answer_payload_and_404() -> None:
    client = _client(_FakeConversations())
    token = _token(client, uuid.uuid4())
    add = client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        json={
            "role": "assistant",
            "content": "A Pod is …",
            "answer_payload": {"status": "answered"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert add.status_code == 201 and add.json()["answer_payload"]["status"] == "answered"
    missing = client.get(
        "/api/v1/conversations/00000000-0000-0000-0000-000000000000/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert missing.status_code == 404


def test_message_role_validated() -> None:
    client = _client(_FakeConversations())
    token = _token(client, uuid.uuid4())
    bad = client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        json={"role": "system", "content": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bad.status_code == 422  # only user|assistant


def test_feedback_rate_and_flag() -> None:
    fake = _FakeConversations()
    client = _client(fake)
    token = _token(client, uuid.uuid4())
    resp = client.post(
        f"/api/v1/messages/{uuid.uuid4()}/feedback",
        json={"rating": -1, "flagged": True, "reason": "wrong page"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201 and resp.json()["flagged"] is True
    # rating bounds enforced
    bad = client.post(
        f"/api/v1/messages/{uuid.uuid4()}/feedback",
        json={"rating": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bad.status_code == 422


def test_list_feedback_for_failure_analysis() -> None:
    fake = _FakeConversations()
    client = _client(fake)
    token = _token(client, uuid.uuid4())
    resp = client.get(
        "/api/v1/feedback?flagged_only=true", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200 and resp.json()[0]["flagged"] is True
    assert ("list_feedback", True) in fake.calls
