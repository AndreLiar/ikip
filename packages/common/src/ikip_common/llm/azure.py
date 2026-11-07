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

    def __init__(
        self,
        settings: Settings | None = None,
        client: Any = None,
        *,
        batch_size: int = 16,
        max_retries: int = 5,
    ) -> None:
        self._settings = settings or get_settings()
        self._dimensions = self._settings.embedding_dimensions
        self._model_version = self._settings.embedding_model_version
        self._client = client or _make_client(self._settings)
        # Batch + retry so a large document doesn't trip the Azure per-minute quota
        # (S0 tiers are low); 429s are retried with exponential backoff.
        self._batch_size = batch_size
        self._max_retries = max_retries

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        if not texts:
            return []
        items = list(texts)
        vectors: list[Vector] = []
        for i in range(0, len(items), self._batch_size):
            batch = items[i : i + self._batch_size]
            vectors.extend(list(v) for v in self._embed_batch(batch))
        return vectors

    def _embed_batch(self, batch: list[str]) -> list[Vector]:
        import time

        try:
            from openai import RateLimitError

            retryable: tuple[type[BaseException], ...] = (RateLimitError,)
        except ImportError:
            # openai not installed (e.g. an injected fake client in the fast CI job) —
            # nothing to retry; an empty tuple in `except` never matches.
            retryable = ()

        for attempt in range(self._max_retries):
            try:
                return self._client.embed_documents(batch)
            except retryable:
                if attempt == self._max_retries - 1:
                    raise
                time.sleep(min(2**attempt, 30))  # exponential backoff, capped
        return []  # unreachable
