"""SecretsProvider + PiiScrubber ports (Story 6.4) — pure, no network, no Azure."""

from __future__ import annotations

import pytest
from ikip_common.config import Settings
from ikip_common.pii import (
    NullPiiScrubber,
    RegexPiiScrubber,
    build_pii_scrubber,
)
from ikip_common.secrets import EnvSecretsProvider, build_secrets_provider


def _settings(**over) -> Settings:
    base = {
        "DATABASE_URL": "postgresql://u:p@h/db",
        "R2_ACCOUNT_ID": "a",
        "R2_ENDPOINT": "https://a.r2.cloudflarestorage.com",
        "R2_BUCKET": "b",
        "R2_ACCESS_KEY_ID": "ak",
        "R2_SECRET_ACCESS_KEY": "sk",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_SECRET": "x" * 36,
    }
    base.update(over)
    return Settings(**base)


# --- secrets provider ------------------------------------------------------


def test_env_secrets_provider_reads_environ(monkeypatch) -> None:
    monkeypatch.setenv("SOME_SECRET", "s3cr3t")
    p = EnvSecretsProvider()
    assert p.get_secret("SOME_SECRET") == "s3cr3t"
    assert p.get_secret("ABSENT") is None


def test_build_secrets_provider_defaults_to_env_without_vault() -> None:
    assert isinstance(build_secrets_provider(_settings()), EnvSecretsProvider)


def test_build_secrets_provider_falls_back_when_keyvault_sdk_missing() -> None:
    # vault URL set but azure SDK not installed in this env -> graceful env fallback
    p = build_secrets_provider(_settings(AZURE_KEY_VAULT_URL="https://v.vault.azure.net/"))
    try:
        import azure.keyvault.secrets  # noqa: F401
    except ImportError:
        assert isinstance(p, EnvSecretsProvider)


# --- PII scrubber ----------------------------------------------------------


def test_regex_scrubber_redacts_common_pii() -> None:
    s = RegexPiiScrubber()
    out = s.scrub("Contact jean.dupont@acme.fr or +33 1 23 45 67 89 from 10.0.0.1")
    assert "jean.dupont@acme.fr" not in out and "<EMAIL>" in out
    assert "<IP>" in out
    assert "<PHONE>" in out


def test_regex_scrubber_leaves_clean_text() -> None:
    s = RegexPiiScrubber()
    txt = "Fault E42 indicates pump overheat; torque to 40 Nm."
    assert s.scrub(txt) == txt
    assert s.scrub("") == ""


def test_build_pii_scrubber_null_when_disabled() -> None:
    assert isinstance(build_pii_scrubber(_settings(PII_SCRUB=False)), NullPiiScrubber)


def test_build_pii_scrubber_uses_regex_fallback_without_presidio() -> None:
    try:
        import presidio_analyzer  # noqa: F401
    except ImportError:
        assert isinstance(build_pii_scrubber(_settings(PII_SCRUB=True)), RegexPiiScrubber)


@pytest.mark.parametrize(
    "secret_text",
    ["jane@x.com", "4111 1111 1111 1111", "FR7630006000011234567890189"],
)
def test_scrubber_never_leaks_the_raw_value(secret_text) -> None:
    out = RegexPiiScrubber().scrub(f"value: {secret_text}")
    assert secret_text not in out
