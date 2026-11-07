"""IKIP document processing — PDF extraction (two-stage: native → OCR), quality.

Engine adapters (PyMuPDF/Tesseract/Docling) live in `engines` and are imported
lazily; the core models/pipeline/quality here are engine-free and CI-testable.
"""

from ikip_docproc.chunking import ChunkSpec, chunk_document, estimate_tokens
from ikip_docproc.cleaning import clean_text, iter_blocks, normalize_unicode
from ikip_docproc.metadata import (
    DocumentMetadata,
    DocumentType,
    build_metadata,
    classify_document,
)
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
from ikip_docproc.validation import ValidationReport, validate_pages

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
    "clean_text",
    "normalize_unicode",
    "iter_blocks",
    "ChunkSpec",
    "chunk_document",
    "estimate_tokens",
    "DocumentMetadata",
    "DocumentType",
    "build_metadata",
    "classify_document",
    "ValidationReport",
    "validate_pages",
]
