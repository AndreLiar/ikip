"""Ingest SEC XBRL companyfacts into a finance tenant (Epic 8, Story 8.1 wiring, ADR 0030).

Orchestrates the full path the services wouldn't otherwise connect: read companyfacts JSON (saved
by `fetch_sec_xbrl.py`) → extract typed facts (`SecCompanyFactsExtractor`) → link each filing to a
Document/DocumentVersion and persist facts with provenance (`link_and_persist_facts`). Creates the
finance tenant if absent. Idempotent.

Usage:
    uv run --group extraction --group doctor python scripts/dataset/ingest_sec_facts.py \
        --tenant-name corpus-finance-sec --facts-dir eval-results/sec
"""

import argparse
import pathlib
import uuid

from ikip_common.db import make_session_factory
from ikip_common.db.models import Tenant
from ikip_common.finance_ingest import link_and_persist_facts
from sqlalchemy import select


def _get_or_create_tenant(session, name: str) -> uuid.UUID:  # noqa: ANN001
    t = session.execute(select(Tenant).where(Tenant.name == name)).scalar_one_or_none()
    if t is None:
        t = Tenant(name=name)
        session.add(t)
        session.flush()
    return t.id


def main() -> None:
    from ikip_docproc.structured import SecCompanyFactsExtractor

    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant-name", default="corpus-finance-sec")
    ap.add_argument("--facts-dir", default="eval-results/sec")
    ap.add_argument(
        "--taxonomies", default="us-gaap,ffd", help="comma-separated taxonomies to ingest"
    )
    args = ap.parse_args()

    files = sorted(pathlib.Path(args.facts_dir).glob("CIK*.json"))
    if not files:
        print(f"no CIK*.json under {args.facts_dir} — run fetch_sec_xbrl.py first")
        return
    extractor = SecCompanyFactsExtractor(taxonomies=args.taxonomies.split(","))
    sf = make_session_factory()
    totals = {"documents": 0, "versions": 0, "facts": 0}
    with sf() as session:
        tenant_id = _get_or_create_tenant(session, args.tenant_name)
        session.commit()
        for f in files:
            specs = extractor.extract_facts(f.read_bytes())
            counts = link_and_persist_facts(session, tenant_id, specs)
            session.commit()
            for k in totals:
                totals[k] += counts[k]
            print(
                f"  {f.name}: {len(specs)} facts (dropped {extractor.last_dropped}) → "
                f"+{counts['documents']} doc, +{counts['versions']} ver, +{counts['facts']} facts",
                flush=True,
            )
    print(f"\nDONE tenant={args.tenant_name}: {totals}", flush=True)


if __name__ == "__main__":
    main()
