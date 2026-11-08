"""Live Azure OpenAI embedding test (Story 3.2) through our adapter.

Skipped unless RUN_AZURE_LIVE_TESTS=1, AZURE_OPENAI_* are configured, and the
`embeddings` group is installed.
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

_CONFIGURED = os.environ.get("RUN_AZURE_LIVE_TESTS") == "1" and all(
    os.environ.get(k)
    for k in (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_API_VERSION",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
    )
)
pytestmark = pytest.mark.skipif(
    not _CONFIGURED,
    reason="set RUN_AZURE_LIVE_TESTS=1 with AZURE_OPENAI_* to run live tests",
)


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


def test_azure_is_stable() -> None:
    import math

    from ikip_common.llm import AzureOpenAIEmbeddingClient

    client = AzureOpenAIEmbeddingClient()
    a = client.embed(["surchauffe moteur"])[0]
    b = client.embed(["surchauffe moteur"])[0]
    # Same input -> essentially the same direction. Assert cosine similarity ~1 rather
    # than element-wise equality: hosted embeddings aren't bit-identical across calls.
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    assert dot / (na * nb) > 0.9999
