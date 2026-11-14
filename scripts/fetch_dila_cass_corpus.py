"""Fetch French public jurisprudence (Cour de cassation) into R2 for the law tenant.

Source: DILA open data (echanges.dila.gouv.fr/OPENDATA/CASS) — Cour de cassation decisions
under **Licence Ouverte 2.0 (Etalab)**, keyless. The archive is a ~260 MB tar.gz of
JURITEXT*.xml; we STREAM it (`r|gz`, no full download), parse each decision's `<CONTENU>` to
clean text, dedup by checksum, and store tenant-scoped: raw/<tenant>/jurisprudence-fr/<sha>.txt
with provenance `rights="licence-ouverte"` (passes the Story-6.5 gate). Text/plain → the
pipeline's text-first path; FR embedding is handled by the multilingual embedding model.

    uv run --group doctor python scripts/fetch_dila_cass_corpus.py --limit 500
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import tarfile
import uuid
from pathlib import Path

import httpx

DILA_CASS = "https://echanges.dila.gouv.fr/OPENDATA/CASS/"
# Dedicated tenant for the (multilingual) LAW corpus — tenant #7.
LAW_TENANT = uuid.UUID("c0f90000-0000-4000-8000-0000000000a7")
_UA = "IKIP-research/0.1 (thesis; Licence Ouverte corpus)"
_TAG = re.compile(r"<[^>]+>")


class _StreamReader:
    """Minimal file-like adapter over httpx streaming bytes so `tarfile` can read the archive
    sequentially (`r|gz`) without buffering the whole 260 MB in memory or on disk."""

    def __init__(self, chunks) -> None:  # noqa: ANN001
        self._it = iter(chunks)
        self._buf = b""

    def read(self, n: int = -1) -> bytes:
        while n < 0 or len(self._buf) < n:
            try:
                self._buf += next(self._it)
            except StopIteration:
                break
        if n < 0:
            out, self._buf = self._buf, b""
            return out
        out, self._buf = self._buf[:n], self._buf[n:]
        return out


def _latest_archive(client: httpx.Client) -> str | None:
    """The open-data directory lists one or more .tar.gz; take the most recent by name."""
    resp = client.get(DILA_CASS)
    resp.raise_for_status()
    files = sorted(set(re.findall(r'href="([^"]+\.tar\.gz)"', resp.text)))
    return (DILA_CASS + files[-1]) if files else None


def _field(xml: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, re.DOTALL)
    return html.unescape(_TAG.sub(" ", m.group(1))).strip() if m else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--min-chars", type=int, default=400, help="skip near-empty decisions")
    ap.add_argument("--tenant", default=str(LAW_TENANT), help="tenant that owns this corpus")
    ap.add_argument("--out", default="eval-results/corpus_law_fr_manifest.json")
    args = ap.parse_args()

    from ikip_common.storage import ArtifactTier, tier_key
    from ikip_common.storage.r2 import R2ObjectStorage

    storage = R2ObjectStorage()
    client = httpx.Client(headers={"User-Agent": _UA}, follow_redirects=True, timeout=120.0)

    archive = _latest_archive(client)
    if not archive:
        print("no CASS archive found in the open-data directory")
        return 1
    print(f"streaming {archive}")

    seen: set[str] = set()
    manifest: list[dict] = []
    skipped_short = 0

    with client.stream("GET", archive) as resp:
        resp.raise_for_status()
        tar = tarfile.open(fileobj=_StreamReader(resp.iter_bytes()), mode="r|gz")
        for member in tar:
            if len(manifest) >= args.limit:
                break
            if not member.name.endswith(".xml"):
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            xml = extracted.read().decode("utf-8", "replace")
            text = _field(xml, "CONTENU")
            if len(text) < args.min_chars:
                skipped_short += 1
                continue
            checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if checksum in seen:
                continue
            seen.add(checksum)
            # Tenant-scoped text artifact (raw/<tenant>/jurisprudence-fr/<sha>.txt).
            key = tier_key(ArtifactTier.raw, args.tenant, "jurisprudence-fr", f"{checksum}.txt")
            if not storage.exists(key):
                storage.put(key, text.encode("utf-8"), content_type="text/plain")
            juri_id = member.name.split("/")[-1].removesuffix(".xml")
            manifest.append(
                {
                    "juri_id": juri_id,
                    "title": (_field(xml, "TITRE") or juri_id)[:300],
                    "date": _field(xml, "DATE_DEC"),
                    "source": f"https://www.legifrance.gouv.fr/juri/id/{juri_id}",
                    "rights": "licence-ouverte",
                    "lang": "fr",
                    "tenant": args.tenant,
                    "r2_key": key,
                    "checksum": checksum,
                    "bytes": len(text.encode("utf-8")),
                    "content_type": "text/plain",
                }
            )
            print(f"[{len(manifest):>4}/{args.limit}] {key}  ({len(text) // 1000} kch)")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    total_mb = sum(m["bytes"] for m in manifest) / 1_000_000
    print(
        f"\nDONE: {len(manifest)} decisions → R2 raw/{args.tenant}/jurisprudence-fr/, "
        f"{total_mb:.1f} MB; skipped(too-short)={skipped_short}. Manifest -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
