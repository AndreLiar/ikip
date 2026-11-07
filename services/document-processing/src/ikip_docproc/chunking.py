"""Structure-aware chunking with bounded sub-splitting (Story 3.1, ADR 0019). Pure.

Strategy:
  1. Split by structure first — headings open sections; paragraphs are content
     (reuses `iter_blocks` from Story 2.4). A procedure/table stays whole.
  2. Sub-split over-long sections at sentence boundaries, with a small overlap so
     context carries across the cut.
  3. Every chunk keeps its section heading/path + page range -> resolvable
     citations (FR16).

Sizes are in approximate tokens (~4 chars/token until the real tokenizer is wired
in Story 3.2). Engine-free and deterministic -> CI-testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ikip_docproc.cleaning import iter_blocks

# Tunable (ADR 0019). Approximate tokens; 1 token ~= 4 chars.
DEFAULT_MAX_TOKENS = 400
DEFAULT_OVERLAP_TOKENS = 40
_CHARS_PER_TOKEN = 4
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN) if text.strip() else 0


@dataclass
class ChunkSpec:
    """A planned chunk (DB-free): content + section/page back-reference (FR16)."""

    content: str
    section_path: str  # hierarchy path, e.g. "3.2.1" or the heading text
    section_heading: str | None
    ordinal: int  # order within the document
    token_count: int = 0
    page_start: int | None = None
    page_end: int | None = None

    def __post_init__(self) -> None:
        if not self.token_count:
            self.token_count = estimate_tokens(self.content)


@dataclass
class _Section:
    heading: str | None
    path: str
    paragraphs: list[str] = field(default_factory=list)


def _group_into_sections(text: str) -> list[_Section]:
    """Turn (kind, content) blocks into sections: a heading starts a new section;
    paragraphs attach to the current section."""
    sections: list[_Section] = []
    current = _Section(heading=None, path="0")
    for kind, content in iter_blocks(text):
        if kind == "heading":
            if current.paragraphs:
                sections.append(current)
            current = _Section(heading=content, path=content)
        else:
            current.paragraphs.append(content)
    if current.paragraphs or not sections:
        sections.append(current)
    return sections


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_RE.split(text) if s.strip()]


def _pack(units: list[str], *, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Greedily pack sentences into chunks up to max_tokens, with token overlap."""
    chunks: list[str] = []
    buf: list[str] = []
    buf_tokens = 0
    for unit in units:
        ut = estimate_tokens(unit)
        if buf and buf_tokens + ut > max_tokens:
            chunks.append(" ".join(buf))
            # start next buffer with a tail overlap from the end of this one
            tail: list[str] = []
            tail_tokens = 0
            for u in reversed(buf):
                tail_tokens += estimate_tokens(u)
                tail.insert(0, u)
                if tail_tokens >= overlap_tokens:
                    break
            buf = tail
            buf_tokens = sum(estimate_tokens(u) for u in buf)
        buf.append(unit)
        buf_tokens += ut
    if buf:
        chunks.append(" ".join(buf))
    return chunks


def chunk_document(
    text: str,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[ChunkSpec]:
    """Chunk curated text structure-first, sub-splitting over-long sections."""
    specs: list[ChunkSpec] = []
    ordinal = 0
    for section in _group_into_sections(text):
        body = "\n\n".join(section.paragraphs).strip()
        if not body:
            continue
        if estimate_tokens(body) <= max_tokens:
            pieces = [body]
        else:
            pieces = _pack(_sentences(body), max_tokens=max_tokens, overlap_tokens=overlap_tokens)
        for piece in pieces:
            specs.append(
                ChunkSpec(
                    content=piece,
                    section_path=section.path,
                    section_heading=section.heading,
                    ordinal=ordinal,
                )
            )
            ordinal += 1
    return specs
