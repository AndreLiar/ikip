"""Source connectors (Story 2.2) — fetch raw documents from configured sources.

A connector's job is only to *fetch bytes* (+ content type + a stable source id);
parsing/OCR is Story 2.3. This keeps PDF/HTML/CSV/JSON/Excel uniform here — they
are all just bytes at ingestion time. Connectors are Dagster-free and testable.

AC3 (authorized crawling + licensing): a `SourceConfig` carries license/auth flags;
`iter_documents` refuses sources that are not authorized or lack a license.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol


class UnauthorizedSourceError(Exception):
    """Raised when a source is not authorized or lacks licensing metadata."""


@dataclass(frozen=True)
class SourceConfig:
    name: str
    # Explicit opt-in gate — never crawl a source that isn't both authorized
    # and licensed (ties to the data-sources licensing gate / Story 6.5).
    authorized: bool = False
    license: str | None = None
    # File URLs and/or API endpoints that list/return documents.
    urls: list[str] = field(default_factory=list)

    def ensure_allowed(self) -> None:
        if not self.authorized:
            raise UnauthorizedSourceError(f"source '{self.name}' is not authorized")
        if not self.license:
            raise UnauthorizedSourceError(f"source '{self.name}' has no license metadata")


@dataclass(frozen=True)
class SourceDocument:
    source_uri: str  # stable id for the document at the source
    content: bytes
    content_type: str | None = None


class SourceConnector(Protocol):
    """Yields documents from a source (bytes only; parsing is downstream)."""

    def iter_documents(self, config: SourceConfig) -> Iterator[SourceDocument]: ...


# Minimal fetcher surface so tests can inject a fake instead of real HTTP.
class Fetcher(Protocol):
    def get(self, url: str) -> tuple[bytes, str | None]:
        """Return (content, content_type) for `url`."""
        ...


class HttpFetcher:
    """Default fetcher using httpx (file URLs or API endpoints)."""

    def __init__(self, timeout_s: float = 30.0) -> None:
        self._timeout = timeout_s

    def get(self, url: str) -> tuple[bytes, str | None]:
        import httpx

        resp = httpx.get(url, timeout=self._timeout, follow_redirects=True)
        resp.raise_for_status()
        return resp.content, resp.headers.get("content-type")


class HttpSourceConnector:
    """Fetches each configured URL as one document (covers file + API sources)."""

    def __init__(self, fetcher: Fetcher | None = None) -> None:
        self._fetcher = fetcher or HttpFetcher()

    def iter_documents(self, config: SourceConfig) -> Iterator[SourceDocument]:
        config.ensure_allowed()
        for url in config.urls:
            content, ctype = self._fetcher.get(url)
            yield SourceDocument(source_uri=url, content=content, content_type=ctype)
