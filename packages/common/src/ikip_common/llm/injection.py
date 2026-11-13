"""Prompt-injection detection for retrieved content (Story 6.3).

Retrieved document content is UNTRUSTED (it can be attacker-authored). The system's primary
defense is structural — the model only ever sees opaque evidence handles, citations are
resolved server-side, and the `ChatClient` port exposes **no tools / function-calling**, so
the model cannot *act* on an injected instruction (it can only emit claims, which are then
grounding-validated). This module adds defense-in-depth + **observability**: it detects known
prompt-injection / jailbreak patterns in retrieved evidence so the attempt is **logged and
surfaced** (AC3), even though the grounding policy already neutralizes the outcome.

Pure + deterministic (regex over text) → runs in the fast CI gate. It flags *patterns*, never
echoes the raw malicious text.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

# Generic injection / jailbreak indicators (case-insensitive). Deliberately conservative:
# these are instruction-override / exfiltration phrases that have no business in equipment
# documentation, so a match is a strong signal of a poisoned document.
_PATTERNS: tuple[tuple[str, str], ...] = (
    ("ignore_instructions", r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions"),
    ("ignore_safety", r"ignore\s+(all\s+)?(the\s+)?safety\s+(rules|instructions|procedures)"),
    ("disregard", r"disregard\s+(all\s+)?(previous|prior|the)\b"),
    ("system_override", r"system\s+override"),
    ("role_reassign", r"you\s+are\s+now\s+"),
    ("reveal_system_prompt", r"(output|reveal|print|show)\s+(the\s+)?system\s+prompt"),
    (
        "exfiltrate_secrets",
        r"(output|reveal|print|send)\s+.{0,30}(credentials|secrets?|api\s*keys?|tokens?)",
    ),
    ("ignore_context", r"(forget|disregard)\s+(everything|all)\b"),
    ("new_instructions", r"new\s+instructions\s*:"),
)

_COMPILED = tuple((name, re.compile(rx, re.IGNORECASE)) for name, rx in _PATTERNS)

INJECTION_WARNING = (
    "Retrieved content contained suspected prompt-injection patterns; it was treated as "
    "untrusted data and its instructions were not followed."
)


def detect_injection(text: str) -> list[str]:
    """Return the names of injection patterns found in `text` (empty = clean). Never returns
    the matched text itself."""
    if not text:
        return []
    return [name for name, rx in _COMPILED if rx.search(text)]


def scan_evidence(evidence: Mapping[str, str]) -> dict[str, list[str]]:
    """Scan a {handle: text} evidence block. Returns {handle: [pattern, …]} for handles whose
    content looks injected (empty dict = all clean)."""
    found: dict[str, list[str]] = {}
    for handle, text in evidence.items():
        hits = detect_injection(text)
        if hits:
            found[handle] = hits
    return found
