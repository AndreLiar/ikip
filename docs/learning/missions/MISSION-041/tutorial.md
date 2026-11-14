# MISSION-041 — Reproduction tutorial

Run Docling as a container and have IKIP extract a PDF through it.

## Prerequisites
- Docker running. `uv` installed. Repo checked out.

## 1. Start docling-serve
```bash
docker compose -f infrastructure/docker/docker-compose.yml up -d docling
# wait for health (~5–60 s on first start)
curl -s localhost:5001/health          # -> {"status":"ok"}
```
The web UI is at http://localhost:5001 (drop a PDF in by hand to see the same conversion
the app calls). First `docker pull` of `docling-serve-cpu` is ~7 GB.

## 2. Point IKIP at it and extract
```bash
IKIP_PDF_EXTRACTOR=docling IKIP_DOCLING_URL=http://localhost:5001 \
  uv run --group extraction --group docling-serve python - <<'PY'
from ikip_docproc.curation import curate_document
pdf = open("/tmp/sample.pdf","rb").read()      # any PDF
doc = curate_document(pdf, source="demo.pdf", content_type="application/pdf")
print(doc.page_count, "pages,", len(doc.regions), "regions")
print(doc.text[:300])
PY
```
Expected: page count > 0, regions with 4-tuple bboxes, curated text. Unset `IKIP_PDF_EXTRACTOR`
to fall back to the default PyMuPDF→Tesseract path (no container needed).

## 3. Run the tests
```bash
# fast, no container (uses the captured fixture):
uv run --group extraction --group docling-serve pytest services/document-processing/tests/test_docling_client.py -q
# live roundtrip (container must be up):
IKIP_DOCLING_LIVE=1 uv run --group extraction --group docling-serve \
  pytest services/document-processing/tests/test_docling_client.py -q -k live
```

## How it works (the seam)
`curate_document` → `_default_pdf_extractor()` reads `IKIP_PDF_EXTRACTOR`. `docling` →
`DoclingRemoteExtractor` POSTs to `POST /v1/convert/file` with `to_formats=json`; the response's
`document.json_content` (a DoclingDocument) is mapped to `DocumentExtraction`
(`texts→TextRegion`, `tables→TableRef`, grouped by page). Everything downstream (clean, metadata,
version, chunk, embed) is unchanged — it only sees `DocumentExtraction`.

## Troubleshooting
- `curl /health` hangs → container still downloading models; `docker logs ikip-docling`.
- `DoclingConversionError status='failure'` → malformed/empty PDF, or `abort_on_error`; check the
  `errors` in the message.
- `httpx` ImportError → add `--group docling-serve`.
- Apple Silicon: the CPU image runs (arm64); conversions are CPU-bound (seconds per page).

## Teardown
```bash
docker compose -f infrastructure/docker/docker-compose.yml down   # add -v nothing persisted
```
