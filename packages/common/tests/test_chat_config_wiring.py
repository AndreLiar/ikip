"""build_chat_client applies the ACTIVE prompt config's ModelConfig (Story 5.5 follow-up).

The versioned config owns the behavior knobs (reasoning_effort/temperature) so a
promote/rollback actually changes generation; the deployment NAME stays env-owned. Here we
prove the config wins over the environment for the knobs, and that the deployment is NOT
overridden.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in {
        "DATABASE_URL": "postgresql://u:p@h/db",
        "R2_ACCOUNT_ID": "a",
        "R2_ENDPOINT": "https://a.r2.cloudflarestorage.com",
        "R2_BUCKET": "b",
        "R2_ACCESS_KEY_ID": "ak",
        "R2_SECRET_ACCESS_KEY": "sk",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_SECRET": "x" * 36,
        # env asks for a DIFFERENT reasoning effort + a specific deployment name
        "CHAT_REASONING_EFFORT": "high",
        "AZURE_OPENAI_CHAT_DEPLOYMENT": "my-env-deployment",
    }.items():
        monkeypatch.setenv(k, v)
    from ikip_common.config import get_settings

    get_settings.cache_clear()


def test_active_model_config_overrides_env_knobs_but_not_deployment(monkeypatch) -> None:
    import ikip_common.llm as llm
    from ikip_common.llm.prompts import active_prompt_config

    captured = {}

    class _CapturingChat:
        def __init__(self, settings) -> None:  # noqa: ANN001
            captured["settings"] = settings

    monkeypatch.setattr(llm, "AzureChatClient", _CapturingChat)
    llm.build_chat_client()

    s = captured["settings"]
    active = active_prompt_config().model
    # behavior knob comes from the active config (v1 = "minimal"), NOT the env ("high")
    assert s.chat_reasoning_effort == active.reasoning_effort == "minimal"
    assert s.chat_temperature == active.temperature
    # deployment stays env-owned (infra), not forced to the artifact's recorded value
    assert s.azure_openai_chat_deployment == "my-env-deployment"
