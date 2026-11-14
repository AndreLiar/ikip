"""Fetch a second public-domain corpus (ENERGY sector) into R2 for a dedicated tenant.

Source: DOE OSTI (Office of Scientific and Technical Information), open JSON API
(`/api/v1/records`, no scraping / no ToS violation). We take ONLY **Technical Reports**
self-published by DOE (DOI prefix `10.2172/`, no journal) — US-Government-sponsored reports
released by DOE for public distribution, the same category as NTRS (public domain, 17 U.S.C.
§105 for federal authorship; DOE unlimited-release for contractor reports). We explicitly
EXCLUDE journal articles (publisher copyright) so the Story-6.5 licensing gate holds, and
record provenance `rights="public-domain"`.

    uv run --group doctor python scripts/fetch_osti_corpus.py --limit 500

Checksum-addressed R2 keys (raw/osti/<sha256>.pdf) give dedup + idempotency. Writes a
provenance manifest for scripts/seed_ingestion_jobs.py (seed to its OWN tenant).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import uuid
from pathlib import Path

import httpx

OSTI = "https://www.osti.gov"
# Dedicated tenant for the DOE/OSTI energy corpus (tenant #2 — isolated from NTRS #1).
ENERGY_TENANT = uuid.UUID("c0f90000-0000-4000-8000-0000000000a2")
_UA = "IKIP-research/0.1 (thesis; public-domain corpus)"
_CLIENT = httpx.Client(
    headers={"User-Agent": _UA},
    follow_redirects=True,
    timeout=httpx.Timeout(90.0),
)

# Energy / industrial technical families (distinct sector from the NTRS aerospace corpus).
DEFAULT_QUERIES = (
    "reactor maintenance",
    "turbine inspection",
    "pipeline integrity",
    "heat exchanger",
    "pump maintenance",
    "valve testing",
    "boiler operation",
    "power plant operations",
    "corrosion inspection",
    "nondestructive examination",
    "welding procedure",
    "electrical substation",
)


def _search(query: str, page: int, rows: int) -> list[dict]:
    """OSTI technical-report search with retry/backoff on transient 5xx."""
    params = {
        "q": query,
        "product_type": "Technical Report",
        "rows": rows,
        "page": page,
        "sort": "relevance",
    }
    for attempt in range(4):
        try:
            resp = _CLIENT.get(f"{OSTI}/api/v1/records", params=params)
            if resp.status_code >= 500:
                raise httpx.HTTPStatusError("5xx", request=resp.request, response=resp)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as exc:  # noqa: BLE001
            if attempt == 3:
                print(f"    search failed (giving up on this page): {type(exc).__name__}")
                return []
            time.sleep(1.5 * (attempt + 1))
    return []


def _is_public_domain(rec: dict) -> bool:
    """DOE-self-published Technical Report (DOI prefix 10.2172, no journal) → public release.
    Excludes journal articles (publisher copyright) even if they slip past the type filter."""
    if rec.get("product_type") != "Technical Report":
        return False
    if rec.get("journal_name"):
        return False
    doi = (rec.get("doi") or "").strip()
    return doi.startswith("10.2172") or doi == ""


def _fulltext_link(rec: dict) -> str | None:
    for link in rec.get("links") or []:
        if link.get("rel") == "fulltext" and link.get("href"):
            return str(link["href"])
    return None


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--max-mb", type=int, default=25)
    ap.add_argument("--rows", type=int, default=50)
    ap.add_argument("--max-pages", type=int, default=12, help="cap pagination depth per query")
    ap.add_argument("--out", default="eval-results/corpus_energy_manifest.json")
    ap.add_argument("--tenant", default=str(ENERGY_TENANT), help="tenant that owns this corpus")
    ap.add_argument("--sleep", type=float, default=0.3)
    args = ap.parse_args()

    from ikip_common.storage import ArtifactTier, tier_key
    from ikip_common.storage.r2 import R2ObjectStorage

    storage = R2ObjectStorage()
    max_bytes = args.max_mb * 1_000_000
    seen: set[str] = set()
    manifest: list[dict] = []
    skipped_copyright = skipped_other = 0

    for query in DEFAULT_QUERIES:
        if len(manifest) >= args.limit:
            break
        page = 1
        pages = 0
        while len(manifest) < args.limit and pages < args.max_pages:
            results = _search(query, page, args.rows)
            pages += 1
            if not results:
                break
            for rec in results:
                if len(manifest) >= args.limit:
                    break
                if not _is_public_domain(rec):
                    skipped_copyright += 1
                    continue
                link = _fulltext_link(rec)
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
                # Tenant-scoped raw key (consistent with the connector + the curated tier):
                # raw/<tenant>/osti/<checksum>.pdf → per-tenant isolation + deletion (Story 6.5).
                key = tier_key(ArtifactTier.raw, args.tenant, "osti", f"{checksum}.pdf")
                if not storage.exists(key):
                    storage.put(key, data, content_type="application/pdf")
                osti_id = rec.get("osti_id")
                manifest.append(
                    {
                        "osti_id": osti_id,
                        "title": str(rec.get("title", ""))[:300],
                        "source": f"{OSTI}/biblio/{osti_id}",
                        "rights": "public-domain",
                        "tenant": args.tenant,
                        "r2_key": key,
                        "checksum": checksum,
                        "bytes": len(data),
                        "content_type": "application/pdf",
                        "query": query,
                    }
                )
                print(f"[{len(manifest):>4}/{args.limit}] {key}  ({len(data) // 1000} KB)  {query}")
                time.sleep(args.sleep)
            page += 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2))
    total_mb = sum(m["bytes"] for m in manifest) / 1_000_000
    print(
        f"\nDONE: {len(manifest)} PDFs → R2 raw/{args.tenant}/osti/, {total_mb:.1f} MB total; "
        f"skipped(non-public-domain)={skipped_copyright}, skipped(no-pdf/too-big)={skipped_other}. "
        f"Manifest -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
