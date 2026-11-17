"""Generate a multi-hop probe gold set from the single-hop NTRS gold (MISSION-049).

The question we want to MEASURE (not assume): can the fixed single-shot flow handle compositional /
multi-hop questions, or does it structurally need decomposition (Epic 10 / Story 10.5)?

Method — grounded, not invented: combine N existing single-hop `ntrs_gold_v2` cases into ONE
compound question whose `relevant_chunk_ids` is the **union** of the parts. Because the fixed flow
does ONE retrieval for the whole question, `recall@k` on the union measures whether a single
embedding can surface BOTH (BOTH THREE) distinct chunks at once. We know each chunk exists and is
individually retrievable (single-hop recall@5 = 0.89, MISSION-045/047), so a drop is attributable to
the multi-hop structure, not to missing data.

Output: `eval-results/ab/ntrs_multihop_probe_{2,3}hop.json` (same schema as the eval harness gold).
Run: `python -m ikip_common.eval run --gold <probe> --tenant <ntrs> --k 5` and compare recall@k /
abstention to the single-hop baseline.
"""

from __future__ import annotations

import json
from pathlib import Path

_SRC = Path("eval-results/ab/ntrs_gold_v2.json")
_OUT_DIR = Path("eval-results/ab")

# Language-appropriate connector joining the parts of a compound question.
_CONNECTOR = {"en": " Separately, ", "fr": " Par ailleurs, "}


def _combine(cases: list[dict], hops: int, *, lang: str = "en") -> list[dict]:
    """Chain consecutive cases into compound questions of `hops` parts (non-overlapping)."""
    conn = _CONNECTOR.get(lang, _CONNECTOR["en"])
    out: list[dict] = []
    for i in range(0, len(cases) - hops + 1, hops):
        group = cases[i : i + hops]
        # A genuine multi-part user turn: the parts are distinct topics, so answering needs
        # every part's chunk — exactly what single-shot retrieval is stressed by.
        question = conn.join(c["question"].rstrip("?") + "?" for c in group)
        ground_truth = " ".join(c["ground_truth"] for c in group if c.get("ground_truth"))
        chunk_ids: list[str] = []
        for c in group:
            chunk_ids.extend(c.get("relevant_chunk_ids", []))
        out.append(
            {
                "case_key": "mh-" + "-".join(c["case_key"].split("-")[-1] for c in group),
                "question": question,
                "expected_behavior": "answered",  # a multi-step system SHOULD answer every part
                "ground_truth": ground_truth,
                "language": lang,
                "reviewed": False,
                "category": f"multi_hop_{hops}",
                "relevant_chunk_ids": chunk_ids,  # UNION — all parts must be retrieved
            }
        )
    return out


def _combine_offset(cases: list[dict], *, lang: str = "en") -> list[dict]:
    """Extra 2-hop pairs (i, i+half) — a *different* pairing than consecutive, to widen the gold
    (n=9 -> n=18) with distinct compound questions for a less noisy gate (MISSION-047)."""
    conn = _CONNECTOR.get(lang, _CONNECTOR["en"])
    half = len(cases) // 2
    out: list[dict] = []
    for i in range(half):
        a, b = cases[i], cases[i + half]
        out.append(
            {
                "case_key": f"mho-{a['case_key'].split('-')[-1]}-{b['case_key'].split('-')[-1]}",
                "question": a["question"].rstrip("?") + "?" + conn + b["question"],
                "expected_behavior": "answered",
                "ground_truth": " ".join(
                    c["ground_truth"] for c in (a, b) if c.get("ground_truth")
                ),
                "language": lang,
                "reviewed": False,
                "category": "multi_hop_2",
                "relevant_chunk_ids": a.get("relevant_chunk_ids", [])
                + b.get("relevant_chunk_ids", []),
            }
        )
    return out


def main() -> None:
    src = json.loads(_SRC.read_text())
    cases = src["cases"]
    for hops in (2, 3):
        probe = {
            "gold_set_version": f"ntrs-multihop-{hops}hop-v1",
            "language": "en",
            "cases": _combine(cases, hops),
        }
        out = _OUT_DIR / f"ntrs_multihop_probe_{hops}hop.json"
        out.write_text(json.dumps(probe, indent=2))
        print(f"{out}: {len(probe['cases'])} {hops}-hop cases (each needs {hops} distinct chunks)")

    # Wider 2-hop set (consecutive + offset pairings) for a less noisy promote gate.
    wide = {
        "gold_set_version": "ntrs-multihop-2hop-wide-v1",
        "language": "en",
        "cases": _combine(cases, 2) + _combine_offset(cases),
    }
    out = _OUT_DIR / "ntrs_multihop_probe_2hop_wide.json"
    out.write_text(json.dumps(wide, indent=2))
    print(f"{out}: {len(wide['cases'])} 2-hop cases (wide)")

    # FR re-confirm (MISSION-052): the decompose split is language-general, but FR is half the
    # corpora — build an FR 2-hop probe from a reviewed FR gold to gate decomposition in French.
    for name, path in [("assurance_fr", _OUT_DIR / "gold_assurance_fr.json")]:
        if not path.exists():
            continue
        fr = json.loads(path.read_text())["cases"]
        probe = {
            "gold_set_version": f"{name}-multihop-2hop-v1",
            "language": "fr",
            "cases": _combine(fr, 2, lang="fr") + _combine_offset(fr, lang="fr"),
        }
        out = _OUT_DIR / f"{name}_multihop_probe_2hop.json"
        out.write_text(json.dumps(probe, indent=2, ensure_ascii=False))
        print(f"{out}: {len(probe['cases'])} FR 2-hop cases")


if __name__ == "__main__":
    main()
