"""PII detection / anonymization port + adapters (Story 6.4, NFR16).

PII handling goes through the `PiiScrubber` port (ADR 0003): the production adapter is
**Presidio** (open-source, self-hosted — no paid PII service), with a deterministic
regex-based `RegexPiiScrubber` as the CI fallback (no heavy model download) and a
`NullPiiScrubber` no-op. Presidio handles PII ONLY — it is not harm/injection moderation
(that's the safety gate + injection defenses, Stories 5.3/6.3).

`scrub(text)` returns the text with detected PII replaced by typed placeholders
(`<EMAIL>`, `<PHONE>`, …) so content can be logged/captured per policy without leaking PII.
Policy: by default we store HASHES + IDs, not raw content (traces, NFR16); when content is
captured deliberately, it is scrubbed first.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable


@runtime_checkable
class PiiScrubber(Protocol):
    def scrub(self, text: str) -> str:
        """Return `text` with detected PII replaced by typed placeholders."""
        ...


class NullPiiScrubber:
    """No-op (PII scrubbing disabled)."""

    def scrub(self, text: str) -> str:
        return text


# Conservative, deterministic patterns for the CI fallback — emails, phone numbers, IPs,
# IBANs, credit-card-like digit runs. Not exhaustive (Presidio is), but zero-dependency and
# reproducible, so PII policy is testable in the fast gate.
_REGEX_PII: tuple[tuple[str, str], ...] = (
    ("<EMAIL>", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ("<IBAN>", r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"),
    ("<CREDIT_CARD>", r"\b(?:\d[ -]?){13,16}\b"),
    ("<IP>", r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    ("<PHONE>", r"(?<!\d)(?:\+\d{1,3}[ .-]?)?(?:\(?\d{2,4}\)?[ .-]?){2,4}\d{2,4}(?!\d)"),
)
_REGEX_COMPILED = tuple((repl, re.compile(rx)) for repl, rx in _REGEX_PII)


class RegexPiiScrubber:
    """Deterministic regex PII scrubber (CI fallback; no model download)."""

    def scrub(self, text: str) -> str:
        if not text:
            return text
        out = text
        for repl, rx in _REGEX_COMPILED:
            out = rx.sub(repl, out)
        return out


class PresidioPiiScrubber:
    """Presidio analyzer + anonymizer (lazy import; needs the `pii` group).

    [untested live] — exercised via RegexPiiScrubber in CI; a real run needs
    `presidio-analyzer`/`presidio-anonymizer` + their spaCy model.
    """

    def __init__(self, language: str = "en") -> None:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine

        self._lang = language
        self._analyzer = AnalyzerEngine()
        self._anonymizer = AnonymizerEngine()

    def scrub(self, text: str) -> str:
        if not text:
            return text
        results = self._analyzer.analyze(text=text, language=self._lang)
        return self._anonymizer.anonymize(text=text, analyzer_results=results).text


def build_pii_scrubber(settings=None) -> PiiScrubber:  # noqa: ANN001
    """Presidio when installed + enabled, else the deterministic regex fallback.

    Controlled by `PII_SCRUB` (default true → regex fallback at minimum). Set `PII_SCRUB=false`
    for a no-op. Presidio is used when the `pii` group is installed.
    """
    from ikip_common.config import get_settings

    s = settings or get_settings()
    if not getattr(s, "pii_scrub", True):
        return NullPiiScrubber()
    try:
        return PresidioPiiScrubber()
    except ImportError:
        return RegexPiiScrubber()
