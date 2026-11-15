"""Build a MESSY-question gold set from the clean n=18 NTRS gold (MISSION-044 follow-up).

Keep each case's source chunk_id and reference answer IDENTICAL; degrade ONLY the question
phrasing (typos, dropped acronym expansions, vague/colloquial wording) as a real user might type.
This isolates question-quality as the single variable so the query-rewrite A/B is fair: same
target chunk, same correct answer, only the phrasing is messy — the case rewrite is meant to fix.

Usage:
    uv run --group embeddings --group doctor python scripts/dataset/gen_messy_gold.py
"""

import json
import pathlib

from ikip_common.llm import build_chat_client
from ikip_common.llm.base import ChatMessage
from pydantic import BaseModel

SRC = "packages/common/tests/fixtures/gold/ntrs_silver_v2.json"
DST = "eval-results/ab/ntrs_gold_v2_messy.json"

SYS = (
    "You simulate how a hurried, non-expert user would TYPE a question into a search box. "
    "Rewrite the given well-formed question to be MESSY but with the SAME meaning: introduce 1-3 "
    "realistic typos, drop capitalization, use abbreviations/acronyms without expansion, make it "
    "terse or vague (e.g. drop articles, use 'whats'/'how do i'). Do NOT change what is being "
    "asked and do NOT add new constraints. Output only the messy question."
)


class Messy(BaseModel):
    question: str


def main() -> None:
    g = json.loads(pathlib.Path(SRC).read_text())
    chat = build_chat_client()
    out_cases = []
    for c in g["cases"]:
        try:
            m = chat.complete_structured(
                [
                    ChatMessage(role="system", content=SYS),
                    ChatMessage(role="user", content=c["question"]),
                ],
                Messy,
            )
            messy_q = (m.question or "").strip() or c["question"]
        except Exception as e:  # noqa: BLE001
            print("  degrade failed:", str(e)[:70], flush=True)
            messy_q = c["question"]
        nc = dict(c)
        nc["clean_question"] = c["question"]  # keep the original for reference
        nc["question"] = messy_q  # degraded phrasing (same meaning/answer/chunk)
        out_cases.append(nc)
        print(f"  {c['question'][:45]:45s}  ->  {messy_q[:55]}", flush=True)

    out = {
        "gold_set_version": "ntrs-silver-v2-messy",
        "language": "en",
        "note": (
            "Messy-phrasing variant of ntrs_silver_v2 (typos/acronyms/vague). Same "
            "relevant_chunk_ids + ground_truth as the clean set; only `question` is degraded. "
            "For the query-rewrite A/B: rewrite should RECOVER retrieval the raw messy query loses."
        ),
        "cases": out_cases,
    }
    dst = pathlib.Path(DST)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, indent=2))
    print(f"\nWROTE {dst} with {len(out_cases)} messy cases", flush=True)


if __name__ == "__main__":
    main()
