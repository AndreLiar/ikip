"""Visual-element extraction tests (Epic 9, Story 9.1, ADR 0031). Pure."""

from ikip_docproc.models import ExtractionMethod, PageExtraction, PictureRef, TableRef
from ikip_docproc.visual import (
    VISUAL_LOW_CONFIDENCE,
    visual_elements_from_page,
    visual_elements_from_pages,
)


def _page(**kw) -> PageExtraction:  # noqa: ANN003
    return PageExtraction(
        page=kw.get("page", 7),
        text="",
        method=ExtractionMethod.native,
        **{k: v for k, v in kw.items() if k != "page"},
    )


def test_extracts_tables_and_pictures_with_page_and_bbox() -> None:
    page = _page(
        tables=[TableRef(page=7, bbox=(0.1, 0.1, 0.5, 0.4))],
        pictures=[PictureRef(page=7, bbox=(0.2, 0.5, 0.8, 0.9), confidence=0.95)],
    )
    specs = visual_elements_from_page(page)
    kinds = {s.kind for s in specs}
    assert kinds == {"table", "figure"}
    fig = next(s for s in specs if s.kind == "figure")
    assert fig.page == 7 and fig.bbox == (0.2, 0.5, 0.8, 0.9)  # page + region (AC1)


def test_low_confidence_picture_is_flagged() -> None:
    page = _page(pictures=[PictureRef(page=3, bbox=None, confidence=0.4)])
    spec = visual_elements_from_page(page)[0]
    assert spec.confidence == 0.4 and spec.low_confidence is True  # flagged for review (AC3)


def test_high_confidence_not_flagged() -> None:
    page = _page(pictures=[PictureRef(page=3, confidence=VISUAL_LOW_CONFIDENCE + 0.1)])
    assert visual_elements_from_page(page)[0].low_confidence is False


def test_empty_page_yields_nothing() -> None:
    assert visual_elements_from_page(_page()) == []


def test_from_pages_collects_across_pages() -> None:
    pages = [
        _page(page=1, tables=[TableRef(page=1, bbox=(0, 0, 1, 1))]),
        _page(page=2, pictures=[PictureRef(page=2, confidence=0.9)]),
    ]
    specs = visual_elements_from_pages(pages)
    assert {s.page for s in specs} == {1, 2} and len(specs) == 2
