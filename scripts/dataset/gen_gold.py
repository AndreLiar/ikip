"""Generate a silver gold set from REAL chunks for ANY tenant + language (MISSION-045).

Generalises the NTRS generator: for each sampled substantial chunk the LLM writes one SEMANTIC
question answerable *from that chunk* + a concise reference answer, in the corpus language. The
source chunk becomes `relevant_chunk_ids` (recall@k) and the answer feeds Ragas. Degenerate /
positional questions are filtered. Silver until a human spot-reviews it.

Usage:
    uv run --group embeddings --group doctor python scripts/dataset/gen_gold.py \
        --tenant <uuid> --name law_fr --lang fr --target 15 \
        --out eval-results/ab/gold_law_fr.json
"""

import argparse
import json
import pathlib
import re

from ikip_common.llm import build_chat_client
from ikip_common.llm.base import ChatMessage
from pydantic import BaseModel

WORD = re.compile(r"[^\W\d_]{2,}", re.UNICODE)  # unicode letters (keeps FR accents)
# positional / self-referential giveaways to reject, EN + FR
_BAD = (
    "passage",
    "text above",
    "following text",
    "the text",
    "immediately after",
    "value shown",
    "appears after",
    "number after",
    "according to the passage",
    "ce passage",
    "le texte",
    "ci-dessus",
    "ci-dessous",
    "extrait",
    "le document",
    "selon le passage",
    "dans le texte",
)

_SYS = {
    "en": (
        "You write evaluation questions for a retrieval system over technical/legal/financial "
        "documents. Given ONE passage, output a single natural question a real user would ask "
        "that is FULLY and ONLY answerable from this passage, plus a concise correct answer (a "
        "few words to one sentence). The question must be SEMANTIC (about facts/meaning), never "
        "positional or a table lookup; never refer to 'the passage'/'the text'; stand alone."
    ),
    "fr": (
        "Tu rédiges des questions d'évaluation pour un système de recherche documentaire (textes "
        "juridiques/assurance/financiers). À partir d'UN passage, produis UNE question naturelle "
        "qu'un vrai utilisateur poserait, à laquelle on répond PLEINEMENT et UNIQUEMENT grâce à "
        "ce passage, plus une réponse de référence concise (quelques mots à une phrase). La "
        "question doit être SÉMANTIQUE (sur les faits/le sens), jamais positionnelle ni une "
        "recherche dans un tableau ; ne jamais dire « ce passage »/« le texte » ; elle doit se "
        "suffire à elle-même. Rédige la question ET la réponse EN FRANÇAIS."
    ),
}


class QAPair(BaseModel):
    question: str
    answer: str


def good_source(c: str) -> bool:
    c = c.strip()
    if not (250 <= len(c) <= 1600):
        return False
    ns = sum(1 for ch in c if not ch.isspace())
    return ns > 0 and sum(1 for ch in c if ch.isalpha()) / ns >= 0.6 and len(WORD.findall(c)) >= 40


def degenerate(q: str, a: str) -> bool:
    ql = q.lower().strip()
    if len(q) < 15 or len(a.strip()) < 3 or not q.rstrip().endswith("?"):
        return True
    return any(b in ql for b in _BAD)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--name", required=True, help="gold-set short name, e.g. law_fr")
    ap.add_argument("--lang", default="en", choices=["en", "fr"])
    ap.add_argument("--target", type=int, default=15)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from ikip_common.db import make_session_factory
    from sqlalchemy import text as sqltext

    sf = make_session_factory()
    chat = build_chat_client()
    with sf() as s:
        rows = s.execute(
            sqltext(
                "select distinct on (d.id) c.id::text, c.content "
                "from chunk c join section se on se.id=c.section_id "
                "join document_version dv on dv.id=se.document_version_id "
                "join document d on d.id=dv.document_id "
                "where c.tenant_id = cast(:t as uuid) and length(c.content) between 250 and 1600 "
                "order by d.id, c.id"
            ),
            {"t": args.tenant},
        ).all()

    candidates = [(cid, c) for cid, c in rows if good_source(c)]
    step = max(1, len(candidates) // (args.target * 2))
    candidates = candidates[::step]
    print(f"[{args.name}] candidates (1/doc, substantial): {len(candidates)}", flush=True)

    sys_prompt = _SYS[args.lang]
    cases = []
    for cid, content in candidates:
        if len(cases) >= args.target:
            break
        try:
            qa = chat.complete_structured(
                [
                    ChatMessage(role="system", content=sys_prompt),
                    ChatMessage(role="user", content=content),
                ],
                QAPair,
            )
        except Exception as e:  # noqa: BLE001
            print("  gen failed:", str(e)[:70], flush=True)
            continue
        if degenerate(qa.question, qa.answer):
            print(f"  drop degenerate: {qa.question[:55]!r}", flush=True)
            continue
        cases.append(
            {
                "case_key": f"{args.name}-{len(cases) + 1}",
                "question": qa.question.strip(),
                "expected_behavior": "answered",
                "ground_truth": qa.answer.strip(),
                "language": args.lang,
                "reviewed": False,
                "relevant_chunk_ids": [cid],
            }
        )
        print(f"  kept {len(cases):2d}: {qa.question[:70]}", flush=True)

    out = {
        "gold_set_version": f"{args.name}-silver-v1",
        "language": args.lang,
        "note": (
            f"Silver gold from real {args.name} chunks (MISSION-045). relevant_chunk_ids are "
            "dev-DB-specific (live eval against this tenant); questions+answers are portable. "
            "Not human-reviewed unless flagged."
        ),
        "cases": cases,
    }
    dst = pathlib.Path(args.out)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\n[{args.name}] WROTE {dst} with {len(cases)} cases", flush=True)


if __name__ == "__main__":
    main()
