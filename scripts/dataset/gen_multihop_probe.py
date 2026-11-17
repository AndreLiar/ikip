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


def _combine(cases: list[dict], hops: int) -> list[dict]:
    """Chain consecutive cases into compound questions of `hops` parts (non-overlapping)."""
    out: list[dict] = []
    for i in range(0, len(cases) - hops + 1, hops):
        group = cases[i : i + hops]
        # A genuine multi-part user turn: the parts are distinct NTRS topics, so answering needs
        # every part's chunk — exactly what single-shot retrieval is stressed by.
        question = " Separately, ".join(c["question"].rstrip("?") + "?" for c in group)
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
                "language": "en",
                "reviewed": False,
                "category": f"multi_hop_{hops}",
                "relevant_chunk_ids": chunk_ids,  # UNION — all parts must be retrieved
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
        n = len(probe["cases"])
        print(f"{out}: {n} {hops}-hop cases (each needs {hops} distinct chunks)")


if __name__ == "__main__":
    main()
