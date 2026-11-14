"""Fetch a French legal CODE (articles en vigueur) from the DILA LEGI open-data dump.

Source: DILA LEGI (echanges.dila.gouv.fr/OPENDATA/LEGI) — all French codes/laws under
**Licence Ouverte 2.0 (Etalab)**, keyless. The global archive is ~1.26 GB tar.gz; we STREAM
it (`r|gz`, no full download to disk) and keep only the members that belong to the requested
code (`code_en_vigueur/.../<LEGITEXT-id>/article/.../LEGIARTI*.xml`), parsing each article's
`<CONTENU>` to clean text. Stored tenant-scoped: raw/<tenant>/legi-<code>/<sha>.txt,
rights="licence-ouverte", lang="fr". NOTE: one ~1.26 GB stream per run (the keyless cost).

    uv run --group doctor python scripts/fetch_legi_code.py --code assurances --tenant <uuid>
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import tarfile
from pathlib import Path

import httpx

LEGI_DIR = "https://echanges.dila.gouv.fr/OPENDATA/LEGI/"
_UA = "IKIP-research/0.1 (thesis; Licence Ouverte corpus)"
_TAG = re.compile(r"<[^>]+>")

# Well-known LEGITEXT ids of the codes we ingest (one code → one tenant).
CODES: dict[str, tuple[str, str]] = {
    # key: (LEGITEXT id, human label)
    "assurances": ("LEGITEXT000006073984", "Code des assurances"),
    "monetaire-financier": ("LEGITEXT000006072026", "Code monétaire et financier"),
    "consommation": ("LEGITEXT000006069565", "Code de la consommation"),
}


class _StreamReader:
    """File-like adapter over httpx streaming bytes so `tarfile` reads the archive
    sequentially (`r|gz`) without buffering 1.26 GB in memory or on disk."""

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


def _latest_global(client: httpx.Client) -> str | None:
    resp = client.get(LEGI_DIR)
    resp.raise_for_status()
    globals_ = sorted(f for f in re.findall(r'href="([^"]+\.tar\.gz)"', resp.text) if "global" in f)
    return (LEGI_DIR + globals_[-1]) if globals_ else None


def _field(xml: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, re.DOTALL)
    return html.unescape(_TAG.sub(" ", m.group(1))).strip() if m else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", required=True, choices=sorted(CODES), help="which code to ingest")
    ap.add_argument("--tenant", required=True, help="tenant that owns this corpus")
    ap.add_argument("--limit", type=int, default=2000, help="max articles")
    ap.add_argument("--min-chars", type=int, default=120, help="skip near-empty articles")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    legitext, label = CODES[args.code]
    out = Path(args.out or f"eval-results/corpus_legi_{args.code}_manifest.json")

    from ikip_common.storage import ArtifactTier, tier_key
    from ikip_common.storage.r2 import R2ObjectStorage

    storage = R2ObjectStorage()
    client = httpx.Client(headers={"User-Agent": _UA}, follow_redirects=True, timeout=300.0)
    archive = _latest_global(client)
    if not archive:
        print("no LEGI global archive found")
        return 1
    print(f"streaming {archive} — extracting {label} ({legitext})")

    # A code's in-force articles: code_en_vigueur/.../<LEGITEXT-id>/article/.../LEGIARTI*.xml
    needle = f"/{legitext}/"
    seen: set[str] = set()
    manifest: list[dict] = []
    scanned = skipped_short = 0

    with client.stream("GET", archive) as resp:
        resp.raise_for_status()
        tar = tarfile.open(fileobj=_StreamReader(resp.iter_bytes()), mode="r|gz")
        for member in tar:
            if len(manifest) >= args.limit:
                break
            name = member.name
            if "/code_en_vigueur/" not in name or needle not in name:
                continue
            if "/article/" not in name or not name.endswith(".xml"):
                continue
            scanned += 1
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            xml = extracted.read().decode("utf-8", "replace")
            if _field(xml, "ETAT").upper() in ("ABROGE", "PERIME", "ANNULE"):  # drop dead articles
                continue
            text = _field(xml, "CONTENU")
            if len(text) < args.min_chars:
                skipped_short += 1
                continue
            checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if checksum in seen:
                continue
            seen.add(checksum)
            arti_id = name.split("/")[-1].removesuffix(".xml")
            num = _field(xml, "NUM")
            key = tier_key(ArtifactTier.raw, args.tenant, f"legi-{args.code}", f"{checksum}.txt")
            if not storage.exists(key):
                storage.put(key, text.encode("utf-8"), content_type="text/plain")
            manifest.append(
                {
                    "arti_id": arti_id,
                    "title": f"{label} — Article {num}" if num else f"{label} — {arti_id}",
                    "source": f"https://www.legifrance.gouv.fr/codes/article_lc/{arti_id}",
                    "rights": "licence-ouverte",
                    "lang": "fr",
                    "tenant": args.tenant,
                    "r2_key": key,
                    "checksum": checksum,
                    "bytes": len(text.encode("utf-8")),
                    "content_type": "text/plain",
                }
            )
            if len(manifest) % 100 == 0:
                print(f"  [{len(manifest)}] articles kept (scanned {scanned})")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    total_mb = sum(m["bytes"] for m in manifest) / 1_000_000
    print(
        f"\nDONE: {len(manifest)} articles of {label} → R2 raw/{args.tenant}/legi-{args.code}/, "
        f"{total_mb:.1f} MB; scanned={scanned}, skipped(short)={skipped_short}. Manifest -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
