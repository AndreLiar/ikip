# MISSION-041 — Decisions

## D1 — Remote `docling-serve` container vs in-process `docling` lib
- **Requirement:** add Docling as "a Docker image running on my machine" without bloating the
  app process or CI.
- **Chosen:** run `quay.io/docling-project/docling-serve-cpu`; app calls it over HTTP.
- **Why here:** matches the explicit "run it as a container" ask; keeps the ~1 GB of ML models
  out of the Python process and out of the fast CI job; lets the engine scale / move to a GPU
  host later with **zero app change** (just repoint `IKIP_DOCLING_URL`).
- **Alternative:** `pip install docling` and call it in-process.
- **Trade-off:** in-process = one fewer moving part (no container, no network) and offline; but
  heavy install everywhere, slower cold start, couples app lifecycle to model downloads. The
  remote path adds a network hop + a service to run.
- **When the alternative wins:** a packaged batch worker image where you *want* everything in one
  artifact and no sidecar, or fully offline extraction. Both adapters can coexist behind the port.

## D2 — Opt-in behind the `TextExtractor` port; PyMuPDF stays the default
- **Chosen:** `IKIP_PDF_EXTRACTOR=docling` switches the adapter; absent/`pymupdf` = the existing
  two-stage PyMuPDF→Tesseract path.
- **Why:** ADR 0012 local-first/$0 posture — don't force a container on every dev/CI run; the
  default must work with no infra. ADR 0021 — libraries live behind ports, so swapping is config,
  not code. No existing caller/test changes behaviour.
- **Alternative:** make Docling the default (richer tables/layout out of the box).
- **Trade-off:** better default fidelity vs a hard container dependency for the basic path and a
  heavier, slower default. Rejected for MVP; revisit if table-heavy manuals dominate the corpus.

## D3 — Request `to_formats=json` and map the DoclingDocument (not just markdown)
- **Chosen:** ask docling-serve for `json_content` and map `texts[].prov[].bbox`/`tables` →
  `TextRegion`/`TableRef` per page.
- **Why:** our `DocumentExtraction` keeps **page references + boxes + table locations**; markdown
  alone throws that away — and structure/tables is precisely why one reaches for Docling.
- **Alternative:** use `md_content`/`text_content` as a single page.
- **Trade-off:** simpler mapping vs losing page refs/tables. The richer mapping costs ~30 lines
  and is unit-tested against a captured fixture, so the complexity is contained.

## D4 — `docling-serve` dep group = `httpx` only
- **Chosen:** new `docling-serve` group with just `httpx`; the old `docling` extra (the heavy lib)
  is kept but documented as "prefer docling-serve".
- **Why:** the remote adapter needs no Docling Python code at all; keeping the group tiny means
  `--group docling-serve` installs in seconds and CI stays fast.
