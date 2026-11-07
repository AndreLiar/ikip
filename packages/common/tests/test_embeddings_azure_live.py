"""Live Azure OpenAI embedding test (Story 3.2) through our adapter.

Skipped unless AZURE_OPENAI_* are configured (and the `embeddings` group installed).
Verifies the real adapter (AzureOpenAIEmbeddingClient wrapping LangChain's
AzureOpenAIEmbeddings) returns 512-dim vectors (ADR 0020) and is deterministic.
Not run in the fast CI `validate` job; run locally / in an integration job.
"""

import os

import pytest
from dotenv import find_dotenv, load_dotenv

# Load the repo-root .env so AZURE_OPENAI_* are visible locally (no-op in CI, which
# has no .env -> the test skips).
load_dotenv(find_dotenv(usecwd=True))

_CONFIGURED = all(
    os.environ.get(k)
    for k in (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_API_VERSION",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
    )
)
pytestmark = pytest.mark.skipif(not _CONFIGURED, reason="AZURE_OPENAI_* not configured")


def test_azure_embeds_at_512_dims() -> None:
    from ikip_common.llm import AzureOpenAIEmbeddingClient

    client = AzureOpenAIEmbeddingClient()
    assert client.dimensions == 512

    vectors = client.embed(
        [
            "Le code défaut E42 indique une surchauffe du moteur de la pompe.",
            "Procédure de redémarrage après arrêt d'urgence.",
        ]
    )
    assert len(vectors) == 2
    assert all(len(v) == 512 for v in vectors)
    # distinct inputs -> distinct vectors
    assert vectors[0] != vectors[1]


def test_azure_is_deterministic() -> None:
    from ikip_common.llm import AzureOpenAIEmbeddingClient

    client = AzureOpenAIEmbeddingClient()
    a = client.embed(["surchauffe moteur"])[0]
    b = client.embed(["surchauffe moteur"])[0]
    # same input -> (near-)identical vector
    assert max(abs(x - y) for x, y in zip(a, b, strict=True)) < 1e-6
