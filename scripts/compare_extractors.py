"""Benchmark the extraction engines on REAL NTRS manuals and calibrate the hybrid router.

Four pipelines, same clipped input per doc (first K pages, so Docling's CPU cost stays
bounded and the comparison is apples-to-apples):

  pymupdf+tesseract — two-stage native→Tesseract OCR (the old default)
  pymupdf+indra     — two-stage native→Indra OCR      (Indra vs Tesseract, same OCR pages)
  docling           — whole-doc Docling via docling-serve
  hybrid            — per-page router (native / Indra OCR / Docling), + route distribution

For each doc we record text yield (chars/words), tables found, pages that hit OCR/layout,
wall time, and how much the texts agree (token Jaccard vs pymupdf+tesseract baseline).

    docker compose -f infrastructure/docker/docker-compose.yml up -d docling
    uv run --group extraction --group docling-serve --group indra --group doctor \
        python scripts/compare_extractors.py --count 4 --pages 6

Writes eval-results/extractor_comparison.{json,md}.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

_WORD = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _WORD.findall(text)}


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    union = len(ta | tb)
    return len(ta & tb) / union if union else 0.0


def _clip_pdf(raw: bytes, max_pages: int) -> tuple[bytes, int, int]:
    import pymupdf

    doc = pymupdf.open(stream=raw, filetype="pdf")
    original = doc.page_count
    keep = min(max_pages, original)
    doc.select(list(range(keep)))
    return doc.tobytes(), original, keep


def _metrics(extraction, seconds: float) -> dict:  # noqa: ANN001
    from ikip_docproc.models import ExtractionMethod

    text = extraction.text
    pages = extraction.pages
    return {
        "status": "ok",
        "pages": len(pages),
        "chars": len(text),
        "words": len(_WORD.findall(text)),
        "tables": sum(len(getattr(p, "tables", [])) for p in pages),
        "ocr_pages": sum(1 for p in pages if p.method is ExtractionMethod.ocr),
        "layout_pages": sum(1 for p in pages if p.method is ExtractionMethod.docling),
        "seconds": round(seconds, 2),
        "_text": text,
    }


def _run(fn) -> dict:  # noqa: ANN001
    t0 = time.perf_counter()
    try:
        extraction = fn()
        return _metrics(extraction, time.perf_counter() - t0)
    except Exception as exc:  # noqa: BLE001 — record, keep benchmarking
        return {
            "status": "error",
            "error": str(exc)[:200],
            "seconds": round(time.perf_counter() - t0, 2),
        }


def _select(manifest: list[dict], count: int) -> list[dict]:
    pool = [e for e in manifest if 100_000 <= e.get("bytes", 0) <= 4_000_000]
    pool.sort(key=lambda e: e.get("bytes", 0))
    if len(pool) <= count:
        return pool
    step = len(pool) / count
    return [pool[int(i * step)] for i in range(count)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="eval-results/corpus_manifest.json")
    ap.add_argument("--count", type=int, default=4)
    ap.add_argument("--pages", type=int, default=6)
    ap.add_argument(
        "--keys", default="", help="comma-separated r2_keys to benchmark (overrides sampling)"
    )
    ap.add_argument("--docling-url", default="http://localhost:5001")
    ap.add_argument("--out", default="eval-results/extractor_comparison")
    args = ap.parse_args()

    from ikip_common.storage import R2ObjectStorage
    from ikip_docproc.docling_client import DoclingRemoteExtractor
    from ikip_docproc.engines import (
        IndraOcrEngine,
        PdfExtractor,
        PyMuPDFExtractor,
        TesseractOcrEngine,
    )
    from ikip_docproc.routing import DoclingLayoutEngine, HybridPdfExtractor, classify_page

    manifest = json.loads(Path(args.manifest).read_text())
    if args.keys:
        wanted = set(args.keys.split(","))
        sample = [e for e in manifest if e["r2_key"] in wanted]
    else:
        sample = _select(manifest, args.count)
    storage = R2ObjectStorage()

    # Build engines once (Indra/Docling load state is reused across docs).
    tesseract = TesseractOcrEngine()
    indra = IndraOcrEngine()
    docling = DoclingRemoteExtractor(args.docling_url, timeout=600.0)
    pipelines = {
        "pymupdf+tesseract": lambda b: PdfExtractor(ocr_engine=tesseract).extract(b),
        "pymupdf+indra": lambda b: PdfExtractor(ocr_engine=indra).extract(b),
        "docling": lambda b: docling.extract(b),
        "hybrid": lambda b: HybridPdfExtractor(
            native=PyMuPDFExtractor(), ocr=indra, layout=DoclingLayoutEngine(docling)
        ).extract(b),
    }

    print(
        f"benchmarking {len(sample)} docs × {len(pipelines)} pipelines, "
        f"clipped to {args.pages} pages\n"
    )
    rows: list[dict] = []
    for i, entry in enumerate(sample, 1):
        title = (entry.get("title") or entry["r2_key"]).strip()
        print(f"[{i}/{len(sample)}] {title[:66]} ({entry['bytes'] // 1024} KB)")
        clipped, original_pages, kept = _clip_pdf(storage.get(entry["r2_key"]), args.pages)

        # Route distribution from stage-1 signals (what the hybrid router decides).
        native_doc = PyMuPDFExtractor().extract(clipped)
        routes = [classify_page(p).value for p in native_doc.pages]
        route_dist = {r: routes.count(r) for r in ("native", "ocr", "layout")}

        results = {}
        for name, fn in pipelines.items():
            res = _run(lambda fn=fn, b=clipped: fn(b))
            results[name] = res
            s = res.get("status")
            tail = (
                f"{res['chars']}c {res['tables']}tbl ocr={res.get('ocr_pages', 0)} "
                f"lay={res.get('layout_pages', 0)} {res['seconds']}s"
                if s == "ok"
                else f"ERROR {res.get('error')}"
            )
            print(f"    {name:18s} {tail}")

        base = results["pymupdf+tesseract"].get("_text", "")
        rows.append(
            {
                "title": title,
                "bytes": entry.get("bytes"),
                "original_pages": original_pages,
                "clipped_pages": kept,
                "route_distribution": route_dist,
                "engines": {
                    k: {kk: vv for kk, vv in v.items() if kk != "_text"} for k, v in results.items()
                },
                "jaccard_vs_tesseract": {
                    k: round(_jaccard(base, v.get("_text", "")), 3)
                    for k, v in results.items()
                    if v.get("status") == "ok"
                },
            }
        )

    Path(f"{args.out}.json").write_text(json.dumps(rows, indent=2))
    _write_report(rows, Path(f"{args.out}.md"), args.pages)
    print(f"\nwrote {args.out}.json and {args.out}.md")
    return 0


def _write_report(rows: list[dict], path: Path, pages: int) -> None:
    names = ["pymupdf+tesseract", "pymupdf+indra", "docling", "hybrid"]

    def avg(engine: str, key: str) -> float:
        vals = [
            r["engines"][engine][key] for r in rows if r["engines"][engine].get("status") == "ok"
        ]
        return sum(vals) / len(vals) if vals else 0.0

    out: list[str] = ["# Extractor benchmark on real NTRS manuals\n"]
    out.append(
        f"{len(rows)} public-domain NTRS PDFs, each clipped to the first **{pages} pages** "
        "(identical bytes to every pipeline).\n"
    )
    out.append("## Per-document\n")
    out.append(
        "| Doc | Pages | Pipeline | chars | tables | OCR pg | layout pg | sec | agree vs Tess |"
    )
    out.append("|---|--:|---|--:|--:|--:|--:|--:|--:|")
    for r in rows:
        for n in names:
            e = r["engines"].get(n, {})
            if e.get("status") != "ok":
                out.append(
                    f"| {r['title'][:34]} | {r['clipped_pages']} | {n} | — | — | — | — | "
                    f"{e.get('seconds', '?')} | ERR |"
                )
                continue
            out.append(
                f"| {r['title'][:34]} | {r['clipped_pages']} | {n} | {e['chars']} | "
                f"{e['tables']} | {e['ocr_pages']} | {e['layout_pages']} | {e['seconds']} | "
                f"{r['jaccard_vs_tesseract'].get(n, '-')} |"
            )
    out.append("\n## Averages per pipeline (ok docs)\n")
    out.append("| Pipeline | avg chars | avg tables | avg sec/doc |")
    out.append("|---|--:|--:|--:|")
    for n in names:
        out.append(
            f"| {n} | {avg(n, 'chars'):.0f} | {avg(n, 'tables'):.1f} | {avg(n, 'seconds'):.1f} |"
        )
    out.append("\n## Hybrid route distribution (pages sent to each engine)\n")
    tot = {"native": 0, "ocr": 0, "layout": 0}
    for r in rows:
        for k in tot:
            tot[k] += r["route_distribution"].get(k, 0)
    total_pages = sum(tot.values()) or 1
    out.append(
        f"- native (PyMuPDF): {tot['native']} pages "
        f"({100 * tot['native'] // total_pages}%)\n"
        f"- ocr (Indra): {tot['ocr']} pages ({100 * tot['ocr'] // total_pages}%)\n"
        f"- layout (Docling): {tot['layout']} pages "
        f"({100 * tot['layout'] // total_pages}%)"
    )
    path.write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
