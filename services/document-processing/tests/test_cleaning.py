"""Cleaning/normalization tests (Story 2.4 AC1). Pure."""

from ikip_docproc.cleaning import clean_text, iter_blocks, normalize_unicode


def test_strips_control_chars_and_nfc() -> None:
    out = normalize_unicode("abc\x00\x07def")
    assert out == "abcdef"


def test_dehyphenates_across_line_breaks() -> None:
    assert clean_text("mainten-\nance") == "maintenance"


def test_collapses_whitespace_and_blank_lines() -> None:
    raw = "Title\n\n\n\nLine  with   spaces   \n\n\n next"
    out = clean_text(raw)
    assert "   " not in out
    assert "\n\n\n" not in out
    assert out.startswith("Title")


def test_normalizes_crlf() -> None:
    assert "\r" not in clean_text("a\r\nb\r\nc")


def test_iter_blocks_detects_headings_vs_paragraphs() -> None:
    text = clean_text(
        "3.2 Fault Handling\n\n"
        "This paragraph explains the procedure in a full sentence with punctuation.\n\n"
        "Safety Warnings"
    )
    blocks = iter_blocks(text)
    kinds = {content: kind for kind, content in blocks}
    assert kinds["3.2 Fault Handling"] == "heading"
    assert kinds["Safety Warnings"] == "heading"
    assert any(k == "paragraph" for k, _ in blocks)
