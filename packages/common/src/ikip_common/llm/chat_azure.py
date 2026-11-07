"""Azure OpenAI chat adapter for the ChatClient port (Story 3.5, ADR 0022/0021).

Wraps LangChain's `AzureChatOpenAI` behind our `ChatClient` port and uses
`with_structured_output(schema)` so the model returns a validated pydantic object.
Lazy-imports langchain (like the embedding adapter). gpt-5.4-mini is reasoning-capable;
`reasoning_effort` (from Settings) tunes depth vs cost/latency. Temperature is 0 for
determinism. Credentials/deployment come from Settings — never hard-coded.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ikip_common.config import Settings, get_settings
from ikip_common.llm.azure import AzureConfigError
from ikip_common.llm.base import ChatMessage, SchemaT

# Reasoning-model families (tuned by reasoning_effort; temperature fixed at 1).
_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _reasoning_model(deployment: str | None) -> bool:
    """True if the deployment name denotes a reasoning model. Heuristic by prefix;
    override by naming the deployment accordingly if a future model breaks it."""
    name = (deployment or "").lower()
    return name.startswith(_REASONING_PREFIXES)


def _chat_kwargs(settings: Settings) -> dict[str, Any]:
    """Build AzureChatOpenAI kwargs from Settings, sending only the knob the model
    supports: reasoning_effort for reasoning models, temperature for the rest. Setting
    a temperature on a reasoning model is rejected here (ADR 0022) — not left to a 400.
    Pure (no network, no SDK import) so it is unit-testable."""
    missing = [
        name
        for name, val in {
            "AZURE_OPENAI_ENDPOINT": settings.azure_openai_endpoint,
            "AZURE_OPENAI_API_KEY": settings.azure_openai_api_key,
            "AZURE_OPENAI_API_VERSION": settings.azure_openai_api_version,
            "AZURE_OPENAI_CHAT_DEPLOYMENT": settings.azure_openai_chat_deployment,
        }.items()
        if not val
    ]
    if missing:
        raise AzureConfigError(f"Azure OpenAI chat not configured; missing: {', '.join(missing)}")

    deployment = settings.azure_openai_chat_deployment
    kwargs: dict[str, Any] = {
        "azure_endpoint": settings.azure_openai_endpoint,
        "api_key": settings.azure_openai_api_key.get_secret_value(),  # type: ignore[union-attr]
        "api_version": settings.azure_openai_api_version,
        "azure_deployment": deployment,
    }
    if _reasoning_model(deployment):
        if settings.chat_temperature is not None:
            raise AzureConfigError(
                f"temperature is not supported by reasoning model '{deployment}'; "
                "unset CHAT_TEMPERATURE or use a non-reasoning model (e.g. gpt-4.1-mini)."
            )
        kwargs["reasoning_effort"] = settings.chat_reasoning_effort
    elif settings.chat_temperature is not None:
        kwargs["temperature"] = settings.chat_temperature
    return kwargs


def _make_chat(settings: Settings) -> Any:
    from langchain_openai import AzureChatOpenAI

    return AzureChatOpenAI(**_chat_kwargs(settings))


class AzureChatClient:
    """ChatClient backed by LangChain's AzureChatOpenAI, behind our port."""

    def __init__(self, settings: Settings | None = None, client: Any = None) -> None:
        self._settings = settings or get_settings()
        self._model_version = self._settings.azure_openai_chat_deployment or "unknown"
        self._client = client or _make_chat(self._settings)

    @property
    def model_version(self) -> str:
        return self._model_version

    def complete_structured(
        self, messages: Sequence[ChatMessage], schema: type[SchemaT]
    ) -> SchemaT:
        structured = self._client.with_structured_output(schema)
        lc_messages = [(m.role, m.content) for m in messages]
        return structured.invoke(lc_messages)
