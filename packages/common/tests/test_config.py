"""Hermetic tests for the config layer (Story 1.2 AC3).

No live services: env is monkey-patched, `.env` loading disabled, so these run
anywhere (incl. CI) without secrets.
"""

import pytest
from ikip_common.config import Settings
from pydantic import ValidationError

# Minimal set of required env vars for a valid Settings instance.
_REQUIRED = {
    "DATABASE_URL": "postgresql://u:p@host/db",
    "R2_ACCOUNT_ID": "acct",
    "R2_ENDPOINT": "https://acct.r2.cloudflarestorage.com",
    "R2_BUCKET": "ikip-test",
    "R2_ACCESS_KEY_ID": "ak",
    "R2_SECRET_ACCESS_KEY": "sk",
    "REDIS_URL": "redis://localhost:6379/0",
    "JWT_SECRET": "test-secret-0123456789abcdef0123456789",
}


_R2_KEYS = (
    "R2_ACCOUNT_ID",
    "R2_ENDPOINT",
    "R2_BUCKET",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
)


def test_loads_required(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _REQUIRED.items():
        monkeypatch.setenv(k, v)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.r2_bucket == "ikip-test"
    assert s.r2_region == "auto"  # default applied
    assert s.database_url.endswith("/db")


def test_missing_required_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    # Only set some; omit R2_* -> validation must raise.
    monkeypatch.setenv("DATABASE_URL", _REQUIRED["DATABASE_URL"])
    monkeypatch.setenv("REDIS_URL", _REQUIRED["REDIS_URL"])
    for k in _R2_KEYS:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_secrets_are_masked(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _REQUIRED.items():
        monkeypatch.setenv(k, v)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    # Secret must never leak via repr/str.
    assert "sk" not in repr(s.r2_secret_access_key)
    assert "sk" not in str(s)
    assert s.r2_secret_access_key.get_secret_value() == "sk"


def test_optional_azure_defaults_none(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _REQUIRED.items():
        monkeypatch.setenv(k, v)
    for k in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.azure_openai_endpoint is None
    assert s.azure_openai_api_key is None
