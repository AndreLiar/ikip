"""Deterministic fake EmbeddingClient for tests (Story 3.2).

Same text -> same unit vector, with no network call, so CI can assert generation,
dimensions, ordering, idempotent re-embedding and version tagging. Vectors are
seeded from a hash of the text and L2-normalized (cosine-friendly), mimicking a
real embedding space's shape without any model. Pure stdlib.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Sequence

from ikip_common.llm.base import Vector


class FakeEmbeddingClient:
    """In-memory, deterministic implementation of the EmbeddingClient port."""

    def __init__(self, *, dimensions: int = 512, model_version: str = "fake-embedding") -> None:
        self._dimensions = dimensions
        self._model_version = f"{model_version}@{dimensions}"

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> Vector:
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        rng = random.Random(seed)
        v = [rng.gauss(0.0, 1.0) for _ in range(self._dimensions)]
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]
