"""Measure what the LEXICAL retrieval arm actually contributes (MISSION-046).

Answers "would true BM25 / a better analyzer help?" with evidence, before paying a second
datastore's cost (ADR 0004). Isolates the lexical arm (not hybrid — the vector arm would mask it)
and measures recall@5 against each FR gold under two query types and two text-search configs:

  - natural-language questions (what users ask)  — the gold questions verbatim
  - keyword/identifier queries (BM25's strength)  — distinctive refs/terms extracted from the
    gold chunk, simulating an exact-term search

  - `simple` config (current, no stemming) vs `french` config (stemming/accent-folding)

Free + deterministic (recall@5 on relevant_chunk_ids; no Azure). Run:
    uv run --group doctor python scripts/probe_lexical_value.py
"""

import json
import re

from ikip_common.db import make_session_factory
from sqlalchemy import text as sqltext

CORPORA = [
    ("law_fr", "a7"),
    ("assurance_fr", "a3"),
    ("banque_finance_fr", "a6"),
    ("credit_conso_fr", "a5"),
]
GOLD = "packages/common/tests/fixtures/gold/{}_silver_v1.json"
TENANT = "c0f90000-0000-4000-8000-0000000000{}"

# article/decree refs + numeric ids — the exact-term tokens BM25 is meant to rank well
_REF = re.compile(
    r"(?:article\s+)?[LRD]\.?\s?\d[\d\-]*|d[ée]cret\s+n[°o]\s?[\d\-]+|\d{2,4}-\d{2,4}", re.I
)


def keyword_query(text: str) -> str:
    refs = _REF.findall(text)
    if refs:
        return " ".join(refs[:2])
    longest = sorted(set(re.findall(r"[^\W\d_]{6,}", text)), key=len, reverse=True)[:3]
    return " ".join(longest)


def lexical_top5(session, tenant: str, query: str, cfg: str) -> list[str]:  # noqa: ANN001
    """Lexical-only top-5 via ts_rank over an on-the-fly to_tsvector(cfg, content)."""
    if not query.strip():
        return []
    return (
        session.execute(
            sqltext(
                f"select c.id::text from chunk c where c.tenant_id = cast(:t as uuid) "
                f"and to_tsvector('{cfg}', c.content) @@ websearch_to_tsquery('{cfg}', :q) "
                f"order by ts_rank(to_tsvector('{cfg}', c.content), "
                f"websearch_to_tsquery('{cfg}', :q)) desc limit 5"
            ),
            {"t": tenant, "q": query},
        )
        .scalars()
        .all()
    )


def main() -> None:
    sf = make_session_factory()
    cols = f"{'NL simple':>10s} {'NL french':>10s} {'KW simple':>10s} {'KW french':>10s}"
    hdr = f"{'corpus':18s} {cols}"
    print(hdr)
    print("-" * len(hdr))
    with sf() as s:
        for name, suf in CORPORA:
            tenant = TENANT.format(suf)
            cases = json.loads(open(GOLD.format(name)).read())["cases"]  # noqa: SIM115
            nl_s = nl_f = kw_s = kw_f = n = 0
            for c in cases:
                want = c["relevant_chunk_ids"][0]
                n += 1
                # natural-language question
                nl_s += want in lexical_top5(s, tenant, c["question"], "simple")
                nl_f += want in lexical_top5(s, tenant, c["question"], "french")
                # keyword/identifier query built from the gold chunk
                src = (
                    s.execute(
                        sqltext("select content from chunk where id = cast(:i as uuid)"),
                        {"i": want},
                    ).scalar()
                    or ""
                )
                kq = keyword_query(src)
                kw_s += want in lexical_top5(s, tenant, kq, "simple")
                kw_f += want in lexical_top5(s, tenant, kq, "french")
            row = f"{nl_s / n:>10.3f} {nl_f / n:>10.3f} {kw_s / n:>10.3f} {kw_f / n:>10.3f}"
            print(f"{name:18s} {row}")
    print(
        "\nNL = natural-language question (what users ask); KW = keyword/identifier query "
        "(BM25's strength). Lexical-only recall@5."
    )


if __name__ == "__main__":
    main()
