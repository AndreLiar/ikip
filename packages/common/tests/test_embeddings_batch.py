"""AzureOpenAIEmbeddingClient batching (Story 3.2 hardening) — pure, no network.

A large document must not be sent as one giant embeddings call (trips the Azure S0
per-minute quota → 429). The adapter splits inputs into batches; this injects a fake
LangChain client to assert the batch sizes + preserved order/count. (429 retry/backoff
is exercised by the live pipeline run.)
"""

import pytest
from ikip_common.config import Settings
from ikip_common.llm.azure import AzureOpenAIEmbeddingClient
from ikip_common.resilience import CircuitBreaker, CircuitOpenError, CircuitState


def _settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        DATABASE_URL="postgresql://u:p@h/db",
        R2_ACCOUNT_ID="a",
        R2_ENDPOINT="e",
        R2_BUCKET="b",
        R2_ACCESS_KEY_ID="k",
        R2_SECRET_ACCESS_KEY="s",
        REDIS_URL="redis://h",
        JWT_SECRET="x" * 32,
        AZURE_OPENAI_EMBEDDING_DEPLOYMENT="text-embedding-3-small",
        EMBEDDING_DIMENSIONS=4,
    )


class _FakeLC:
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    def embed_documents(self, batch: list[str]) -> list[list[float]]:
        self.batch_sizes.append(len(batch))
        return [[float(i)] * 4 for i, _ in enumerate(batch)]


def test_embed_splits_into_batches_preserving_count() -> None:
    fake = _FakeLC()
    client = AzureOpenAIEmbeddingClient(_settings(), client=fake, batch_size=16)
    vectors = client.embed([f"t{i}" for i in range(40)])

    assert len(vectors) == 40  # one vector per input
    assert fake.batch_sizes == [16, 16, 8]  # batched, not one 40-input call
    assert all(len(v) == 4 for v in vectors)


class _DownLC:
    """A LangChain client that always fails (a sustained Azure outage)."""

    def __init__(self) -> None:
        self.calls = 0

    def embed_documents(self, batch: list[str]) -> list[list[float]]:  # noqa: ARG002
        self.calls += 1
        raise RuntimeError("azure down")


def test_breaker_opens_and_fast_fails_on_sustained_embedding_failure() -> None:
    # #145: once open, embed() fast-fails WITHOUT calling Azure again (no backoff pileup).
    fake = _DownLC()
    cb = CircuitBreaker(failure_threshold=2, name="test")
    client = AzureOpenAIEmbeddingClient(
        _settings(), client=fake, batch_size=16, max_retries=1, breaker=cb
    )

    for _ in range(2):
        with pytest.raises(RuntimeError):
            client.embed(["t"])  # two real failures trip the breaker
    assert cb.state is CircuitState.OPEN
    calls_before = fake.calls

    with pytest.raises(CircuitOpenError):
        client.embed(["t"])  # fast-fail — the downstream client is NOT called again
    assert fake.calls == calls_before


def test_embed_empty_is_noop() -> None:
    fake = _FakeLC()
    assert AzureOpenAIEmbeddingClient(_settings(), client=fake).embed([]) == []
    assert fake.batch_sizes == []
