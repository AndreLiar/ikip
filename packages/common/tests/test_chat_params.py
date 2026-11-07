"""Chat model parameter wiring + validation (Story 3.5, ADR 0022) — pure, no network.

Tests the pure `_chat_kwargs` / `_reasoning_model` logic: reasoning models get
reasoning_effort and reject an explicit temperature; non-reasoning models (fallback
gpt-4.1-mini) accept temperature and don't receive reasoning_effort.
"""

import pytest
from ikip_common.config import Settings
from ikip_common.llm.azure import AzureConfigError
from ikip_common.llm.chat_azure import _chat_kwargs, _reasoning_model


def _settings(**over) -> Settings:
    base = {
        "DATABASE_URL": "postgresql://u:p@h/db",
        "R2_ACCOUNT_ID": "a",
        "R2_ENDPOINT": "e",
        "R2_BUCKET": "b",
        "R2_ACCESS_KEY_ID": "k",
        "R2_SECRET_ACCESS_KEY": "s",
        "REDIS_URL": "redis://h",
        "JWT_SECRET": "x" * 32,
        "AZURE_OPENAI_ENDPOINT": "https://x.openai.azure.com/",
        "AZURE_OPENAI_API_KEY": "key",
        "AZURE_OPENAI_API_VERSION": "2024-10-21",
        "AZURE_OPENAI_CHAT_DEPLOYMENT": "gpt-5.4-mini",
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def test_reasoning_model_detection() -> None:
    assert _reasoning_model("gpt-5.4-mini")
    assert _reasoning_model("o3-mini")
    assert not _reasoning_model("gpt-4.1-mini")
    assert not _reasoning_model(None)


def test_reasoning_model_gets_reasoning_effort_not_temperature() -> None:
    kwargs = _chat_kwargs(_settings(CHAT_REASONING_EFFORT="low"))
    assert kwargs["reasoning_effort"] == "low"
    assert "temperature" not in kwargs


def test_reasoning_model_rejects_explicit_temperature() -> None:
    with pytest.raises(AzureConfigError, match="temperature is not supported"):
        _chat_kwargs(_settings(CHAT_TEMPERATURE=0.2))


def test_non_reasoning_model_accepts_temperature() -> None:
    kwargs = _chat_kwargs(
        _settings(AZURE_OPENAI_CHAT_DEPLOYMENT="gpt-4.1-mini", CHAT_TEMPERATURE=0.2)
    )
    assert kwargs["temperature"] == 0.2
    assert "reasoning_effort" not in kwargs  # not sent to a non-reasoning model


def test_non_reasoning_model_without_temperature_sends_neither() -> None:
    kwargs = _chat_kwargs(_settings(AZURE_OPENAI_CHAT_DEPLOYMENT="gpt-4.1-mini"))
    assert "temperature" not in kwargs
    assert "reasoning_effort" not in kwargs


def test_missing_config_raises() -> None:
    with pytest.raises(AzureConfigError, match="not configured"):
        _chat_kwargs(_settings(AZURE_OPENAI_CHAT_DEPLOYMENT=""))
