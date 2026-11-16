"""Fetch SEC EDGAR XBRL companyfacts for a finance corpus (Epic 8, Story 8.1, ADR 0030).

SEC EDGAR data is produced by the U.S. government and is **public domain** — clean for the
licensing gate (Story 6.5). The companyfacts API pre-normalizes XBRL into JSON; SEC requires a
descriptive `User-Agent`. Saves one JSON per CIK under the output dir (gitignored eval/data area)
for the structured extractor to parse (`ikip_docproc.structured.SecCompanyFactsExtractor`).

Usage:
    uv run python scripts/dataset/fetch_sec_xbrl.py --out eval-results/sec \
        --cik 320193 --cik 789019        # Apple, Microsoft
"""

import argparse
import pathlib
import time
import urllib.request

API = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:0>10}.json"
# SEC requires a descriptive UA with contact; identify the project honestly.
UA = "IKIP Research (academic; kanmegnea@gmail.com)"


def fetch_company_facts(cik: str, timeout: int = 30) -> bytes:
    url = API.format(cik=cik)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed SEC host
        import gzip
        import io

        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        return raw


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cik", action="append", required=True, help="SEC CIK (repeatable)")
    ap.add_argument("--out", default="eval-results/sec")
    ap.add_argument("--sleep", type=float, default=0.3, help="politeness delay between requests")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for cik in args.cik:
        try:
            data = fetch_company_facts(cik)
        except Exception as e:  # noqa: BLE001
            print(f"  CIK {cik}: FAILED ({str(e)[:80]})", flush=True)
            continue
        dst = out / f"CIK{cik:0>10}.json"
        dst.write_bytes(data)
        print(f"  CIK {cik}: wrote {dst} ({len(data):,} bytes)", flush=True)
        time.sleep(args.sleep)
    print(f"done -> {out}", flush=True)


if __name__ == "__main__":
    main()
