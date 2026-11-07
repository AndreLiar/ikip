"""Azure OpenAI adapter for the EmbeddingClient port (Story 3.2, ADR 0007/0020/0021).

Per ADR 0021 we reuse LangChain's mature `AzureOpenAIEmbeddings` component, but
*behind* our own `EmbeddingClient` port — the domain never imports LangChain. The
SDK is lazy-imported (like boto3 in the R2 adapter) so the core package stays light
and fake-client tests need no LangChain. Deployment, dimension and credentials come
from Settings (.env / Key Vault) — never hard-coded. We request the reduced
dimension (512) explicitly (Matryoshka, ADR 0020).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ikip_common.config import Settings, get_settings
from ikip_common.llm.base import Vector


class AzureConfigError(RuntimeError):
    """Raised when Azure OpenAI settings needed for embeddings are missing."""


def _make_client(settings: Settings) -> Any:
    from langchain_openai import AzureOpenAIEmbeddings

    missing = [
        name
        for name, val in {
            "AZURE_OPENAI_ENDPOINT": settings.azure_openai_endpoint,
            "AZURE_OPENAI_API_KEY": settings.azure_openai_api_key,
            "AZURE_OPENAI_API_VERSION": settings.azure_openai_api_version,
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": settings.azure_openai_embedding_deployment,
        }.items()
        if not val
    ]
    if missing:
        raise AzureConfigError(f"Azure OpenAI not configured; missing: {', '.join(missing)}")

    return AzureOpenAIEmbeddings(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key.get_secret_value(),  # type: ignore[union-attr]
        api_version=settings.azure_openai_api_version,
        azure_deployment=settings.azure_openai_embedding_deployment,
        dimensions=settings.embedding_dimensions,
    )


class AzureOpenAIEmbeddingClient:
    """EmbeddingClient backed by LangChain's AzureOpenAIEmbeddings, behind our port."""

    def __init__(self, settings: Settings | None = None, client: Any = None) -> None:
        self._settings = settings or get_settings()
        self._dimensions = self._settings.embedding_dimensions
        self._model_version = self._settings.embedding_model_version
        self._client = client or _make_client(self._settings)

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        if not texts:
            return []
        # LangChain's embed_documents preserves input order and returns list[list[float]].
        return [list(v) for v in self._client.embed_documents(list(texts))]
