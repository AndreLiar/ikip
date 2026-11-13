"""Fetch a public-domain technical-document corpus into R2 (raw tier).

Source: NASA Technical Reports Server (NTRS) — US-Government technical works are public
domain (17 U.S.C. §105). We ONLY take records flagged `copyright == "PUBLIC"` and record
provenance `rights="public-domain"` so they pass the Story-6.5 licensing gate; the NTRS
JSON API is open (no scraping / no ToS violation). Real technical PDFs (native + scanned,
tables) across several topics → exercises the full ingestion pipeline at scale.

    uv run --group doctor python scripts/fetch_public_domain_corpus.py --limit 500

Checksum-addressed R2 keys (raw/ntrs/<sha256>.pdf) give natural dedup + idempotency
(re-runs skip objects already uploaded). Writes a provenance manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import httpx

NTRS = "https://ntrs.nasa.gov"
_UA = "IKIP-research/0.1 (thesis; public-domain corpus)"
_CLIENT = httpx.Client(
    headers={"User-Agent": _UA},
    follow_redirects=True,
    timeout=httpx.Timeout(60.0),
)

# Diverse technical queries → equipment/maintenance/instrumentation families.
DEFAULT_QUERIES = (
    "maintenance manual",
    "operations handbook",
    "inspection procedure",
    "troubleshooting guide",
    "repair manual",
    "calibration procedure",
    "instrument measurement",
    "equipment technical manual",
)


def _search(query: str, page_from: int, page_size: int) -> list[dict]:
    """NTRS search with retry/backoff on transient 5xx (the API 503s under load)."""
    params = {"q": query, "page.size": page_size, "page.from": page_from, "sort": "relevance"}
    for attempt in range(4):
        try:
            resp = _CLIENT.get(f"{NTRS}/api/citations/search", params=params)
            if resp.status_code >= 500:
                raise httpx.HTTPStatusError("5xx", request=resp.request, response=resp)
            resp.raise_for_status()
            return resp.json().get("results", [])
        except Exception as exc:  # noqa: BLE001
            if attempt == 3:
                print(f"    search failed (giving up on this page): {type(exc).__name__}")
                return []
            time.sleep(1.5 * (attempt + 1))
    return []


def _download(url: str, *, max_bytes: int) -> bytes | None:
    try:
        resp = _CLIENT.get(url)
        resp.raise_for_status()
        data = resp.content
    except Exception as exc:  # noqa: BLE001
        print(f"    download failed: {type(exc).__name__}")
        return None
    if len(data) > max_bytes:
        print(f"    skip: > {max_bytes // 1_000_000} MB")
        return None
    if not data[:5].startswith(b"%PDF"):
        print("    skip: not a PDF")
        return None
    return data


def _pdf_link(result: dict) -> str | None:
    for d in result.get("downloads", []):
        if d.get("mimetype") == "application/pdf" and not d.get("draft", False):
            link = (d.get("links") or {}).get("pdf")
            if link:
                return NTRS + link
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--max-mb", type=int, default=25)
    ap.add_argument("--page-size", type=int, default=50)
    ap.add_argument("--max-pages", type=int, default=12, help="cap pagination depth per query")
    ap.add_argument("--out", default="eval-results/corpus_manifest.json")
    ap.add_argument("--sleep", type=float, default=0.3)
    args = ap.parse_args()

    from ikip_common.storage.r2 import R2ObjectStorage

    storage = R2ObjectStorage()
    max_bytes = args.max_mb * 1_000_000
    seen: set[str] = set()
    manifest: list[dict] = []
    skipped_copyright = skipped_other = 0

    for query in DEFAULT_QUERIES:
        if len(manifest) >= args.limit:
            break
        page_from = 0
        pages = 0
        while len(manifest) < args.limit and pages < args.max_pages:
            results = _search(query, page_from, args.page_size)
            pages += 1
            if not results:
                break
            for res in results:
                if len(manifest) >= args.limit:
                    break
                # public-domain predicate: NTRS `distribution == PUBLIC` +
                # copyright.determinationType == GOV_PUBLIC_USE_PERMITTED (US-Gov work, §105).
                determination = (res.get("copyright") or {}).get("determinationType")
                is_public = (
                    res.get("distribution") == "PUBLIC"
                    and determination == "GOV_PUBLIC_USE_PERMITTED"
                )
                if not is_public:
                    skipped_copyright += 1
                    continue
                ntrs_id = res.get("id")
                link = _pdf_link(res)
                if not link:
                    skipped_other += 1
                    continue
                data = _download(link, max_bytes=max_bytes)
                if data is None:
                    skipped_other += 1
                    continue
                checksum = hashlib.sha256(data).hexdigest()
                if checksum in seen:
                    continue  # exact dedup
                seen.add(checksum)
                key = f"raw/ntrs/{checksum}.pdf"
                if not storage.exists(key):
                    storage.put(key, data, content_type="application/pdf")
                manifest.append(
                    {
                        "ntrs_id": ntrs_id,
                        "title": str(res.get("title", ""))[:300],
                        "source": f"{NTRS}/citations/{ntrs_id}",
                        "rights": "public-domain",
                        "r2_key": key,
                        "checksum": checksum,
                        "bytes": len(data),
                        "query": query,
                    }
                )
                print(f"[{len(manifest):>4}/{args.limit}] {key}  ({len(data) // 1000} KB)  {query}")
                time.sleep(args.sleep)
            page_from += args.page_size

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2))
    total_mb = sum(m["bytes"] for m in manifest) / 1_000_000
    print(
        f"\nDONE: {len(manifest)} PDFs uploaded to R2 (raw/ntrs/), {total_mb:.1f} MB total; "
        f"skipped(copyright)={skipped_copyright}, skipped(other)={skipped_other}. "
        f"Manifest -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
