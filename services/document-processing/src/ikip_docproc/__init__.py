"""IKIP document processing — PDF extraction (two-stage: native → OCR), quality.

Engine adapters (PyMuPDF/Tesseract/Docling) live in `engines` and are imported
lazily; the core models/pipeline/quality here are engine-free and CI-testable.
"""

from ikip_docproc.models import (
    DocumentExtraction,
    ExtractionMethod,
    PageExtraction,
    TableRef,
)
from ikip_docproc.pipeline import (
    NativeExtractor,
    OcrEngine,
    extract_document,
)
from ikip_docproc.quality import is_low_quality, needs_ocr, score_page

__all__ = [
    "DocumentExtraction",
    "ExtractionMethod",
    "PageExtraction",
    "TableRef",
    "NativeExtractor",
    "OcrEngine",
    "extract_document",
    "is_low_quality",
    "needs_ocr",
    "score_page",
]
