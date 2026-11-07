"""Text cleaning & normalization (Story 2.4 AC1). Pure — CI-tested.

Turns raw extracted text into consistent curated text while preserving structure
(paragraphs/headings). Conservative on purpose: we normalize noise (hyphenation
across line breaks, stray whitespace, control chars, unicode form) without
destroying meaningful layout.
"""

from __future__ import annotations

import re
import unicodedata

# A line that looks like a heading: short, no trailing sentence punctuation,
# often numbered ("3.2 Fault handling"). Heuristic, used to preserve structure.
_HEADING_RE = re.compile(r"^(?:\d+(?:\.\d+)*\s+)?[A-Z][^.!?]{0,80}$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# word-hyphen-newline-word  ->  joined word (PDF line-break hyphenation)
_HYPHEN_BREAK_RE = re.compile(r"(\w)-\n(\w)")
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")
_MULTINEWLINE_RE = re.compile(r"\n{3,}")


def normalize_unicode(text: str) -> str:
    """NFC-normalize and strip control chars (keep \\n and \\t)."""
    text = unicodedata.normalize("NFC", text)
    return _CONTROL_RE.sub("", text)


def clean_text(text: str) -> str:
    """Produce consistent curated text, preserving paragraph/heading structure."""
    if not text:
        return ""
    text = normalize_unicode(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)  # de-hyphenate across line breaks
    # Collapse runs of spaces/tabs, trim each line, drop trailing whitespace.
    lines = [_MULTISPACE_RE.sub(" ", ln).strip() for ln in text.split("\n")]
    text = "\n".join(lines)
    text = _MULTINEWLINE_RE.sub("\n\n", text)  # at most one blank line between blocks
    return text.strip()


def looks_like_heading(line: str) -> bool:
    line = line.strip()
    return bool(line) and bool(_HEADING_RE.match(line))


def iter_blocks(text: str) -> list[tuple[str, str]]:
    """Split curated text into (kind, content) blocks where kind in {heading, paragraph}.
    Structure-aware so downstream chunking (Epic 3) can respect sections."""
    blocks: list[tuple[str, str]] = []
    for para in filter(None, (p.strip() for p in text.split("\n\n"))):
        single_line = "\n" not in para
        kind = "heading" if single_line and looks_like_heading(para) else "paragraph"
        blocks.append((kind, para))
    return blocks
