"""AzureOpenAIEmbeddingClient batching (Story 3.2 hardening) — pure, no network.

A large document must not be sent as one giant embeddings call (trips the Azure S0
per-minute quota → 429). The adapter splits inputs into batches; this injects a fake
LangChain client to assert the batch sizes + preserved order/count. (429 retry/backoff
is exercised by the live pipeline run.)
"""

from ikip_common.config import Settings
from ikip_common.llm.azure import AzureOpenAIEmbeddingClient


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


def test_embed_empty_is_noop() -> None:
    fake = _FakeLC()
    assert AzureOpenAIEmbeddingClient(_settings(), client=fake).embed([]) == []
    assert fake.batch_sizes == []
