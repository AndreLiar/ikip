"""EmbeddingClient port (Story 3.2, ADR 0007/0020).

The embedding slice of the future `LLMClient` (ADR 0007); `complete`/`stream` land
with the grounded-answer graph (Story 3.5). The default adapter is Azure OpenAI; a
deterministic `FakeEmbeddingClient` backs the same port so generation + versioning
logic is CI-testable without a network call — the same ports-and-adapters pattern
as ObjectStorage/R2 (ADR 0003).

A client carries its own `model_version`: embeddings are only comparable within one
model+dimension, so every stored vector is tagged with it (FR14, ADR 0020).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

# A single embedding vector. Dimension is fixed per model_version (e.g. 512).
Vector = list[float]

SchemaT = TypeVar("SchemaT", bound=BaseModel)


@runtime_checkable
class EmbeddingClient(Protocol):
    """Port that turns text into vectors."""

    @property
    def model_version(self) -> str:
        """Identifies the model + dimension, e.g. 'text-embedding-3-small@512'.
        Stored on each embedding row so re-embedding is additive, not destructive."""
        ...

    @property
    def dimensions(self) -> int:
        """Length of every vector this client returns."""
        ...

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        """Embed a batch of texts; returns one vector per input, in order."""
        ...


@dataclass(frozen=True)
class ChatMessage:
    """One message in a chat completion. role ∈ {'system','user','assistant'}."""

    role: str
    content: str


@runtime_checkable
class ChatClient(Protocol):
    """Port for grounded-answer generation (the `complete` slice of LLMClient).

    `complete_structured` returns a validated instance of `schema` (a pydantic model)
    — we always use structured output so the model emits typed claims + evidence
    markers rather than free prose (Story 3.5). The Azure adapter wraps LangChain's
    AzureChatOpenAI; a deterministic `FakeChatClient` backs the same port for CI."""

    @property
    def model_version(self) -> str: ...

    def complete_structured(
        self, messages: Sequence[ChatMessage], schema: type[SchemaT]
    ) -> SchemaT: ...
