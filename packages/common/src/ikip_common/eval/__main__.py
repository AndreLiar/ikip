"""Evaluation CLI (Story 3.6, ADR 0016).

Documented, reproducible commands:

  # live run against a gold set (real Azure + DB) -> writes runs/<ts>.json + latest.json
  uv run --group embeddings python -m ikip_common.eval run \
      --gold packages/common/tests/fixtures/gold/v1.json --tenant <uuid> --k 5 --out eval-results

  # fail (exit 1) if latest.json regressed vs the approved baseline.json
  uv run python -m ikip_common.eval check --out eval-results --tolerance 0.02

  # approve the current latest.json as the new reference
  uv run python -m ikip_common.eval promote --out eval-results

  # Story 5.3 critical safety gate — deterministic, no network; exit 1 blocks release
  uv run --group embeddings python -m ikip_common.eval safety \
      --gold packages/common/tests/fixtures/safety/v1.json

The per-push CI gate does NOT call `run`/`check` (no network): they run the harness with a
FakeChatClient over versioned fixtures (see tests). `safety` is the exception — it is a
required, network-free release gate (scripted fakes) wired into CI. This CLI is otherwise
for live/manual runs.
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


def _safety(args: argparse.Namespace) -> int:
    """Run the critical safety-abstention gate (Story 5.3). Exit 1 on any failure so it
    blocks release in CI. Deterministic + network-free (scripted fakes)."""
    from ikip_common.eval.safety import format_report, load_safety_cases, run_safety_suite

    version, cases = load_safety_cases(args.gold)
    report = run_safety_suite(cases, safety_set_version=version)
    print(format_report(report))
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "safety.json").write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.all_passed else 1


def _safety_passed(gold: str) -> bool:
    from ikip_common.eval.safety import load_safety_cases, run_safety_suite

    version, cases = load_safety_cases(gold)
    return run_safety_suite(cases, safety_set_version=version).all_passed


def _config(args: argparse.Namespace) -> int:
    """Versioned prompt/model config registry (Story 5.5): list / show / activate
    (rollback) / promote (gated on retrieval + groundedness + safety)."""
    from ikip_common.eval.report import load_json
    from ikip_common.llm.prompts import (
        PromotionBlockedError,
        build_prompt_publisher,
        default_registry,
        evaluate_gates,
    )

    reg = default_registry()
    active = reg.active_version()

    if args.action == "list":
        for v in reg.versions():
            mark = " (active)" if v == active else ""
            print(f"{v}{mark}  {reg.get(v).content_hash()[:12]}")
        return 0

    if args.action == "show":
        print(json.dumps(reg.get(args.version).to_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.action == "activate":  # AC4: rollback = activate a prior version
        reg.activate(args.version)
        print(f"active prompt config -> {args.version}")
        return 0

    if args.action == "promote":
        out = Path(args.eval)
        latest = out / "latest.json"
        aggregate = load_json(latest)["aggregate"] if latest.exists() else None
        gates = evaluate_gates(aggregate, safety_passed=_safety_passed(args.safety_gold))
        print(f"gates: {gates.summary()}")
        try:
            reg.promote(args.version, gates=gates, publisher=build_prompt_publisher())
        except PromotionBlockedError as exc:
            print(f"BLOCKED: {exc}")
            return 1
        print(f"promoted + activated {args.version} (synced to prompt backend if configured)")
        return 0

    return 2


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

    p_safety = sub.add_parser("safety", help="run the critical safety-abstention gate (Story 5.3)")
    p_safety.add_argument("--gold", default="packages/common/tests/fixtures/safety/v1.json")
    p_safety.add_argument("--out", default="", help="optional dir to write safety.json")
    p_safety.set_defaults(func=_safety)

    p_config = sub.add_parser("config", help="versioned prompt/model config registry (Story 5.5)")
    csub = p_config.add_subparsers(dest="action", required=True)
    csub.add_parser("list", help="list versions (marks the active one)")
    c_show = csub.add_parser("show", help="print a config version")
    c_show.add_argument("--version", required=True)
    c_act = csub.add_parser("activate", help="switch/rollback the active version (AC4)")
    c_act.add_argument("--version", required=True)
    c_prom = csub.add_parser("promote", help="promote a version iff gates pass (AC3)")
    c_prom.add_argument("--version", required=True)
    c_prom.add_argument("--eval", default="eval-results", help="dir with latest.json aggregate")
    c_prom.add_argument("--safety-gold", default="packages/common/tests/fixtures/safety/v1.json")
    p_config.set_defaults(func=_config)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
