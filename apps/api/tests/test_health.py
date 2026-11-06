"""Health endpoint tests (Story 1.3 AC4).

Hermetic: dependency checks are mocked (no live services), and settings are
provided via monkeypatched env so `create_app()` doesn't fail-fast in CI.
"""

import pytest
from fastapi.testclient import TestClient
from ikip_common.doctor import CheckResult

_ENV = {
    "DATABASE_URL": "postgresql://u:p@host/db",
    "R2_ACCOUNT_ID": "acct",
    "R2_ENDPOINT": "https://acct.r2.cloudflarestorage.com",
    "R2_BUCKET": "ikip-test",
    "R2_ACCESS_KEY_ID": "ak",
    "R2_SECRET_ACCESS_KEY": "sk",
    "REDIS_URL": "redis://localhost:6379/0",
}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _ENV.items():
        monkeypatch.setenv(k, v)
    # get_settings is cached; clear so each test re-reads env.
    from ikip_common.config import get_settings

    get_settings.cache_clear()


# ---- unit: status logic -------------------------------------------------


def test_status_ok_when_all_pass() -> None:
    from ikip_api.health import _to_status

    body = _to_status([CheckResult("neon", True, "ok"), CheckResult("r2", None, "skip")])
    assert body.status == "ok"
    assert {d.service for d in body.dependencies} == {"neon", "r2"}


def test_status_degraded_when_any_fails() -> None:
    from ikip_api.health import _to_status

    body = _to_status([CheckResult("neon", True, "ok"), CheckResult("redis", False, "boom")])
    assert body.status == "degraded"


# ---- integration: endpoint via TestClient (deps mocked) -----------------


def _client(monkeypatch: pytest.MonkeyPatch, results: list[CheckResult]) -> TestClient:
    import ikip_api.health as health_mod

    monkeypatch.setattr(health_mod, "run_checks", lambda *a, **k: results)
    from ikip_api.main import create_app

    return TestClient(create_app())


def test_health_200_when_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, [CheckResult("neon", True, "ok"), CheckResult("r2", True, "ok")])
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "ikip-api"
    assert any(d["service"] == "neon" for d in data["dependencies"])


def test_health_503_when_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, [CheckResult("redis", False, "conn refused")])
    resp = client.get("/api/v1/health")
    assert resp.status_code == 503
    assert resp.json()["status"] == "degraded"
