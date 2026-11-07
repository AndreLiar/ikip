"""LLM/embedding ports + adapters (Story 3.2, ADR 0007).

Port: `EmbeddingClient`. Adapters: `AzureOpenAIEmbeddingClient` (default, lazy-imports
the openai SDK) and `FakeEmbeddingClient` (deterministic, CI). `build_embedding_client`
returns the production (Azure) client from Settings.
"""

from __future__ import annotations

from ikip_common.config import Settings, get_settings
from ikip_common.llm.azure import AzureConfigError, AzureOpenAIEmbeddingClient
from ikip_common.llm.base import EmbeddingClient, Vector
from ikip_common.llm.fake import FakeEmbeddingClient


def build_embedding_client(settings: Settings | None = None) -> EmbeddingClient:
    """Build the production embedding client (Azure OpenAI). Raises AzureConfigError
    if the AZURE_OPENAI_* settings are missing. Tests inject FakeEmbeddingClient."""
    return AzureOpenAIEmbeddingClient(settings or get_settings())


__all__ = [
    "EmbeddingClient",
    "Vector",
    "AzureOpenAIEmbeddingClient",
    "AzureConfigError",
    "FakeEmbeddingClient",
    "build_embedding_client",
]
