"""LLM ports + adapters (Stories 3.2, 3.5; ADR 0007/0020/0022).

Ports: `EmbeddingClient`, `ChatClient`, `GroundingValidator`. Adapters wrap LangChain
behind the ports (ADR 0021) and lazy-import heavy SDKs; `Fake*` back the same ports
deterministically for CI. `build_*_client` return the production (Azure) clients.

Note: the request-time graph (`answer.py`), hybrid retrieval (`hybrid.py`) and the
`IkipRetriever` (`retriever.py`) import langchain_core/langgraph at module load, so
they are NOT re-exported here — import them directly where the `embeddings` group is
installed. Everything exported here is light enough for the fast CI `validate` job.
"""

from __future__ import annotations

from ikip_common.config import Settings, get_settings
from ikip_common.llm.azure import AzureConfigError, AzureOpenAIEmbeddingClient
from ikip_common.llm.base import ChatClient, ChatMessage, EmbeddingClient, Vector
from ikip_common.llm.chat_azure import AzureChatClient
from ikip_common.llm.fake import FakeEmbeddingClient
from ikip_common.llm.fake_chat import FakeChatClient, FakeGroundingValidator
from ikip_common.llm.grounding import GroundingValidator, LLMGroundingValidator
from ikip_common.llm.schemas import Claim, ClaimVerdict, GroundedAnswer, GroundingResult


def build_embedding_client(settings: Settings | None = None) -> EmbeddingClient:
    """Build the production embedding client (Azure OpenAI). Raises AzureConfigError
    if the AZURE_OPENAI_* settings are missing. Tests inject FakeEmbeddingClient."""
    return AzureOpenAIEmbeddingClient(settings or get_settings())


def build_chat_client(settings: Settings | None = None) -> ChatClient:
    """Build the production chat client (Azure OpenAI). Raises AzureConfigError if the
    AZURE_OPENAI_* chat settings are missing. Tests inject FakeChatClient."""
    return AzureChatClient(settings or get_settings())


__all__ = [
    # embeddings
    "EmbeddingClient",
    "Vector",
    "AzureOpenAIEmbeddingClient",
    "AzureConfigError",
    "FakeEmbeddingClient",
    "build_embedding_client",
    # chat + grounding
    "ChatClient",
    "ChatMessage",
    "AzureChatClient",
    "FakeChatClient",
    "build_chat_client",
    "GroundingValidator",
    "LLMGroundingValidator",
    "FakeGroundingValidator",
    # structured outputs
    "Claim",
    "ClaimVerdict",
    "GroundedAnswer",
    "GroundingResult",
]
