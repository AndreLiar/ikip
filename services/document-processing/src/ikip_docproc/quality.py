"""Extraction quality scoring (Story 2.3 AC4). Pure heuristics — no engines.

A page's score reflects how much usable text we got. Scanned/garbled pages score
low and get flagged (and routed to OCR). Tunable thresholds; the goal is to catch
"this page produced almost nothing / looks like noise", not to be perfect.
"""

from __future__ import annotations

# Below this many characters of native text, a page is treated as scanned/empty
# and routed to OCR (stage 2).
MIN_NATIVE_CHARS = 20
# Below this score a page is flagged low-quality for review.
LOW_QUALITY_THRESHOLD = 0.4


def _printable_ratio(text: str) -> float:
    if not text:
        return 0.0
    printable = sum(1 for c in text if c.isprintable() and not c.isspace())
    return printable / len(text)


def score_page(text: str, *, page_char_cap: int = 2000) -> float:
    """Return a 0..1 quality score from extracted text.

    Combines *how much* text (length, capped) with *how clean* it is
    (ratio of printable, non-space chars — low for OCR garble / binary noise).
    """
    if not text.strip():
        return 0.0
    length_component = min(len(text), page_char_cap) / page_char_cap
    cleanliness = _printable_ratio(text)
    return round(0.5 * length_component + 0.5 * cleanliness, 4)


def is_low_quality(score: float, *, threshold: float = LOW_QUALITY_THRESHOLD) -> bool:
    return score < threshold


def needs_ocr(text: str, *, min_chars: int = MIN_NATIVE_CHARS) -> bool:
    """Stage-1 decision: a page with almost no native text is (likely) scanned."""
    return len(text.strip()) < min_chars
