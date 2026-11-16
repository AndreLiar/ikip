"""Vision captioner port (Epic 9, Story 9.2, ADR 0031).

Caption-and-embed turns a diagram/visual-table image into a dense text **caption** (what it shows,
labels, fault codes, relations) which is then embedded with the existing text model and indexed in
the same pgvector store — so visual content is searchable with NO new embedding model and no
storage blowup (ADR 0031). A `VisionCaptioner` is the seam for the vision LLM (Azure GPT-4o vision
adapter lazily, behind `LLMClient`); `FakeVisionCaptioner` backs the same port in CI.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class VisionCaptioner(Protocol):
    """Port: a visual element's image bytes -> a dense text caption for retrieval."""

    def caption(self, image: bytes, *, kind: str | None = None, hint: str | None = None) -> str: ...


class FakeVisionCaptioner:
    """Deterministic captioner for CI: returns a scripted caption (optionally per kind)."""

    def __init__(
        self, caption: str = "a technical diagram", *, by_kind: dict | None = None
    ) -> None:
        self._caption = caption
        self._by_kind = by_kind or {}

    def caption(self, image: bytes, *, kind: str | None = None, hint: str | None = None) -> str:  # noqa: ARG002
        return self._by_kind.get(kind, self._caption)
