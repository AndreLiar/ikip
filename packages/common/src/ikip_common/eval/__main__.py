"""Evaluation CLI (Story 3.6, ADR 0016).

Documented, reproducible commands:

  # live run against a gold set (real Azure + DB) -> writes runs/<ts>.json + latest.json
  uv run --group embeddings python -m ikip_common.eval run \
      --gold packages/common/tests/fixtures/gold/v1.json --tenant <uuid> --k 5 --out eval-results

  # fail (exit 1) if latest.json regressed vs the approved baseline.json
  uv run python -m ikip_common.eval check --out eval-results --tolerance 0.02

  # approve the current latest.json as the new reference
  uv run python -m ikip_common.eval promote --out eval-results

The per-push CI gate does NOT call this (no network): it runs the harness with a
FakeChatClient over versioned fixtures (see tests). This CLI is for live/manual runs.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path


def _load_gold(path: str) -> tuple[str, list]:
    from ikip_common.eval.harness import GoldCase

    doc = json.loads(Path(path).read_text())
    cases = [
        GoldCase(
            case_key=c["case_key"],
            question=c["question"],
            expected_behavior=c["expected_behavior"],
            relevant_chunk_ids=c.get("relevant_chunk_ids", []),
        )
        for c in doc["cases"]
    ]
    return doc.get("gold_set_version", "unknown"), cases


def _run(args: argparse.Namespace) -> int:
    from sqlalchemy.orm import Session

    from ikip_common.db.session import make_engine
    from ikip_common.eval.harness import evaluate_dataset
    from ikip_common.eval.report import write_run
    from ikip_common.llm import build_chat_client, build_embedding_client
    from ikip_common.llm.answer import make_hybrid_retrieve

    version, cases = _load_gold(args.gold)
    tenant_id = uuid.UUID(args.tenant)
    with Session(make_engine()) as session:
        retrieve = make_hybrid_retrieve(session, tenant_id, build_embedding_client(), limit=args.k)
        report = evaluate_dataset(
            cases,
            retrieve=retrieve,
            chat_client=build_chat_client(),
            k=args.k,
            gold_set_version=version,
        )
    run_path, latest = write_run(report, args.out)
    print(f"wrote {run_path} and {latest}")
    print(json.dumps(report.aggregate, indent=2, sort_keys=True))
    return 0


def _check(args: argparse.Namespace) -> int:
    from ikip_common.eval.harness import EvalReport, compare_to_baseline
    from ikip_common.eval.report import load_json

    out = Path(args.out)
    baseline_path = out / "baseline.json"
    if not baseline_path.exists():
        print("no baseline.json — nothing to compare (run `promote` to set one)")
        return 0
    latest = load_json(out / "latest.json")
    report = EvalReport(
        gold_set_version=latest["gold_set_version"],
        config=latest["config"],
        aggregate=latest["aggregate"],
        cases=latest["cases"],
    )
    regressions = compare_to_baseline(report, load_json(baseline_path), tolerance=args.tolerance)
    if regressions:
        for r in regressions:
            print(f"REGRESSION {r.metric}: {r.baseline:.4f} -> {r.current:.4f} ({r.delta:+.4f})")
        return 1
    print("no regression vs baseline")
    return 0


def _promote(args: argparse.Namespace) -> int:
    from ikip_common.eval.report import promote

    print(f"promoted latest.json -> {promote(args.out)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ikip_common.eval", description="RAG evaluation (Story 3.6)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="live run against a gold set")
    p_run.add_argument("--gold", required=True)
    p_run.add_argument("--tenant", required=True)
    p_run.add_argument("--k", type=int, default=5)
    p_run.add_argument("--out", default="eval-results")
    p_run.set_defaults(func=_run)

    p_check = sub.add_parser("check", help="compare latest.json to baseline.json")
    p_check.add_argument("--out", default="eval-results")
    p_check.add_argument("--tolerance", type=float, default=0.0)
    p_check.set_defaults(func=_check)

    p_promote = sub.add_parser("promote", help="approve latest.json as baseline.json")
    p_promote.add_argument("--out", default="eval-results")
    p_promote.set_defaults(func=_promote)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
