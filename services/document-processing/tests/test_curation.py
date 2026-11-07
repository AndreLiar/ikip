"""Curation (Story 2.3/2.4 assembly) — pure, no engines, no network."""

from ikip_docproc.curation import curate_document


def test_curate_text_first_cleans_and_extracts_metadata() -> None:
    raw = b"Pump Manual\n\nFault E42: motor overheat.\n\nRev. B"
    doc = curate_document(raw, source="https://x/pump-manual.txt")
    assert "E42" in doc.text
    assert doc.page_count == 1
    assert doc.metadata.revision == "B"  # extract_revision picked it up
    assert doc.metadata.title == "pump manual"  # derived from the source filename


def test_curate_html_strips_tags() -> None:
    raw = b"<html><body><h1>Gearbox</h1><p>Torque &amp; bolts</p><script>x=1</script></body></html>"
    doc = curate_document(raw, source="g.html", content_type="text/html")
    assert "<" not in doc.text and "script" not in doc.text.lower()
    assert "Torque & bolts" in doc.text  # entity unescaped


def test_curate_sniffs_html_without_content_type() -> None:
    # ingestion jobs don't persist content_type, so curation must detect HTML by content
    raw = b"<!doctype html><html><body><h1>Pods</h1><p>A Pod runs containers.</p></body></html>"
    doc = curate_document(raw, source="pods")  # no content_type passed
    assert "<" not in doc.text and "A Pod runs containers." in doc.text


def test_curate_drops_boilerplate_and_keeps_main() -> None:
    raw = (
        b"<!doctype html><html><body>"
        b"<nav>Home Docs Blog Training Versions v1.37 v1.36 English Chinese</nav>"
        b"<header>Cookie banner - hide this notice</header>"
        b"<main><h1>Pods</h1><p>A Pod is the smallest deployable unit.</p></main>"
        b"<footer>Copyright The Authors</footer>"
        b"</body></html>"
    )
    doc = curate_document(raw, source="pods.html", content_type="text/html")
    assert "A Pod is the smallest deployable unit." in doc.text
    # nav/header/footer boilerplate removed (menus, cookie banner, version picker)
    assert "v1.37" not in doc.text and "Cookie banner" not in doc.text
    assert "Copyright" not in doc.text and "Home Docs Blog" not in doc.text


def test_curate_no_revision_leaves_none() -> None:
    doc = curate_document(b"Some manual text without a revision marker.", source="m.txt")
    assert doc.metadata.revision is None  # caller applies a deterministic fallback


def test_curate_with_injected_extractor() -> None:
    class _FakePdf:
        text = "Page one text. Fault E42."
        pages = [object(), object()]

    class _Extractor:
        def extract(self, data: bytes):
            return _FakePdf()

    doc = curate_document(b"%PDF-1.7...", source="m.pdf", extractor=_Extractor())
    assert "E42" in doc.text and doc.page_count == 2  # used the extractor, not text decode
