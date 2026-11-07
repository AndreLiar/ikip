"""Quality-scoring tests (Story 2.3 AC4). Pure — no engines."""

from ikip_docproc.quality import is_low_quality, needs_ocr, score_page


def test_empty_text_scores_zero() -> None:
    assert score_page("") == 0.0
    assert score_page("   \n ") == 0.0


def test_clean_rich_text_scores_high() -> None:
    text = "Maintenance procedure for pump model S7-1500. " * 40
    s = score_page(text)
    assert s > 0.8
    assert not is_low_quality(s)


def test_garbled_text_scores_low() -> None:
    # Mostly non-printable / control noise -> low cleanliness.
    garbled = "\x00\x01\x02\x03" * 50
    assert is_low_quality(score_page(garbled))


def test_needs_ocr_on_sparse_text() -> None:
    assert needs_ocr("")  # empty -> scanned
    assert needs_ocr("12")  # too few chars
    assert not needs_ocr("This page clearly has real native text content.")
