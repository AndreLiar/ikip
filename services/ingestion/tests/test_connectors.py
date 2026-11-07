"""Connector tests (Story 2.2 AC1/AC3). Hermetic: a fake fetcher, no HTTP."""

import pytest
from ikip_ingestion.connectors import (
    HttpSourceConnector,
    SourceConfig,
    UnauthorizedSourceError,
)


class FakeFetcher:
    def __init__(self, data: dict[str, tuple[bytes, str | None]]) -> None:
        self._data = data

    def get(self, url: str) -> tuple[bytes, str | None]:
        return self._data[url]


def test_unauthorized_source_rejected() -> None:
    conn = HttpSourceConnector(FakeFetcher({}))
    cfg = SourceConfig(name="x", authorized=False, license="CC", urls=["u"])
    with pytest.raises(UnauthorizedSourceError):
        list(conn.iter_documents(cfg))


def test_missing_license_rejected() -> None:
    conn = HttpSourceConnector(FakeFetcher({}))
    cfg = SourceConfig(name="x", authorized=True, license=None, urls=["u"])
    with pytest.raises(UnauthorizedSourceError):
        list(conn.iter_documents(cfg))


def test_fetches_each_url_with_content_type() -> None:
    fetcher = FakeFetcher(
        {
            "a.pdf": (b"%PDF-1", "application/pdf"),
            "b.csv": (b"x,y", "text/csv"),
        }
    )
    conn = HttpSourceConnector(fetcher)
    cfg = SourceConfig(name="manuals", authorized=True, license="MIT", urls=["a.pdf", "b.csv"])
    docs = list(conn.iter_documents(cfg))
    assert [d.source_uri for d in docs] == ["a.pdf", "b.csv"]
    assert docs[0].content_type == "application/pdf"
    assert docs[1].content == b"x,y"
