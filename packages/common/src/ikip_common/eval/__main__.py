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

  # Story 5.1/5.2 one-time: seed a real eval corpus, then run against the RESOLVED gold
  # (its relevant_chunk_ids now point at ingested chunks).
  uv run --group embeddings python -m ikip_common.eval seed \
      --tenant <uuid> --out eval-results/failure_modes.resolved.json

  # Story 5.2 Ragas LLM-judged metrics + custom-vs-Ragas comparison (live Azure + DB).
  # Bounded sample in CI, full nightly/on-demand (cost + non-determinism control).
  uv run --group embeddings --group ragas python -m ikip_common.eval compare \
      --gold packages/common/tests/fixtures/gold/failure_modes.json --tenant <uuid> \
      --sample 5 --runs 3 --out eval-results

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
            category=c.get("category", ""),
            ground_truth=c.get("ground_truth"),
            language=c.get("language", doc.get("language", "en")),
            reviewed=c.get("reviewed", False),
            reviewer=c.get("reviewer"),
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


def _live_report(args: argparse.Namespace):  # noqa: ANN201 — (version, cases, EvalReport)
    """Run the deterministic harness over a gold set against real Azure + DB. Shared by the
    `ragas` and `compare` commands so both score the SAME answers/contexts from one run."""
    from sqlalchemy.orm import Session

    from ikip_common.db.session import make_engine
    from ikip_common.eval.harness import evaluate_dataset
    from ikip_common.llm import build_chat_client, build_embedding_client
    from ikip_common.llm.answer import make_hybrid_retrieve
    from ikip_common.telemetry import build_telemetry

    version, cases = _load_gold(args.gold)
    if getattr(args, "sample", 0):
        cases = cases[: args.sample]  # bounded sample (AC5: cost/variance control)
    tenant_id = uuid.UUID(args.tenant)
    with Session(make_engine()) as session:
        retrieve = make_hybrid_retrieve(session, tenant_id, build_embedding_client(), limit=args.k)
        report = evaluate_dataset(
            cases,
            retrieve=retrieve,
            chat_client=build_chat_client(),
            k=args.k,
            gold_set_version=version,
            telemetry=build_telemetry(),  # trace each case -> attach Ragas scores (5.4↔5.2)
        )
    return version, cases, report


def _trace_ids(report) -> dict:  # noqa: ANN001
    return {c["case_key"]: c["trace_id"] for c in report.cases if c.get("trace_id")}


def _samples_from(cases, report):  # noqa: ANN001, ANN202
    from ikip_common.eval.ragas_eval import EvalSample

    gt = {c.case_key: c.ground_truth for c in cases}
    return [
        EvalSample(
            case_key=c["case_key"],
            question=next(x.question for x in cases if x.case_key == c["case_key"]),
            answer=c.get("answer", ""),
            contexts=c.get("contexts", []),
            ground_truth=gt.get(c["case_key"]),
        )
        for c in report.cases
    ]


def _ragas(args: argparse.Namespace) -> int:
    """Live Ragas run over a gold set (Azure judge). Writes ragas.json + pushes scores to
    Langfuse (AC3). [untested live] — needs Azure creds + the `ragas` group."""
    from ikip_common.eval.ragas_eval import build_ragas_evaluator, build_score_publisher

    version, cases, report = _live_report(args)
    samples = _samples_from(cases, report)
    scores = build_ragas_evaluator().evaluate(samples)
    build_score_publisher().publish(
        scores, run_name=f"ragas:{version}", trace_ids=_trace_ids(report)
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "ragas.json").write_text(json.dumps(scores.to_dict(), indent=2, sort_keys=True))
    print(json.dumps(scores.means, indent=2, sort_keys=True))
    return 0


def _compare(args: argparse.Namespace) -> int:
    """Run BOTH metric systems on the same gold set and report agreement/divergence, cost
    and variance (AC4). Writes comparison.json. [untested live] — Azure + `ragas` group."""
    from ikip_common.eval.compare import MetricPair, compare
    from ikip_common.eval.ragas_eval import build_ragas_evaluator, build_score_publisher

    version, cases, report = _live_report(args)
    samples = _samples_from(cases, report)
    evaluator = build_ragas_evaluator()
    runs = [evaluator.evaluate(samples) for _ in range(max(1, args.runs))]
    scores = runs[0]
    build_score_publisher().publish(
        scores, run_name=f"compare:{version}", trace_ids=_trace_ids(report)
    )
    import math

    by_case = {c["case_key"]: c for c in report.cases}
    # Only ANSWERED cases are comparable: Ragas faithfulness is undefined for an abstention
    # (empty answer -> NaN). Abstention correctness is covered by behavior_conformity + the
    # safety gate, not by this groundedness-vs-faithfulness comparison.
    pairs = [
        MetricPair(
            case_key=s.case_key,
            custom_groundedness=by_case[s.case_key]["citation_grounding_coverage"],
            ragas_faithfulness=scores.per_case[s.case_key]["faithfulness"],
        )
        for s in samples
        if by_case[s.case_key]["actual_behavior"] == "answered"
        and not math.isnan(scores.per_case[s.case_key]["faithfulness"])
    ]
    comparison = compare(
        pairs,
        gold_set_version=version,
        ragas_cost_usd=scores.cost_usd,
        ragas_runs=[r.means for r in runs],
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "comparison.json").write_text(json.dumps(comparison.to_dict(), indent=2, sort_keys=True))
    print(json.dumps(comparison.to_dict(), indent=2, sort_keys=True))
    return 0


def _gold_status(args: argparse.Namespace) -> int:
    """Report SME-review provenance + language mix of a gold set (trustworthy-references
    gap). Advisory by default; `--require-reviewed` makes an unreviewed case exit 1 — wire
    that into CI once a gold set is meant to gate."""
    version, cases = _load_gold(args.gold)
    by_lang: dict[str, dict] = {}
    for c in cases:
        b = by_lang.setdefault(c.language, {"n": 0, "reviewed": 0})
        b["n"] += 1
        b["reviewed"] += 1 if c.reviewed else 0
    n_reviewed = sum(1 for c in cases if c.reviewed)
    print(f"gold {version}: {len(cases)} cases, {n_reviewed} SME-reviewed")
    for lang in sorted(by_lang):
        b = by_lang[lang]
        print(f"  [{lang}] {b['reviewed']}/{b['n']} reviewed")
    unreviewed = [c.case_key for c in cases if not c.reviewed]
    if unreviewed:
        print(f"UNREVIEWED ({len(unreviewed)}): {', '.join(unreviewed)}")
    if args.require_reviewed and unreviewed:
        return 1
    return 0


def _seed(args: argparse.Namespace) -> int:
    """Seed a real eval corpus (Story 5.1/5.2) and emit a runnable gold file whose
    `relevant_chunk_ids` point at the ingested chunks. [live] — needs a DB + Azure
    embeddings (`--group embeddings`)."""
    from sqlalchemy.orm import Session

    from ikip_common.db.session import make_engine
    from ikip_common.eval.seed import resolve_gold_ids, seed_corpus
    from ikip_common.llm import build_embedding_client

    tenant_id = uuid.UUID(args.tenant)
    with Session(make_engine()) as session:
        mapping = seed_corpus(session, tenant_id, build_embedding_client())
        session.commit()
    resolved = resolve_gold_ids(json.loads(Path(args.gold).read_text()), mapping)
    Path(args.out).write_text(json.dumps(resolved, indent=2, ensure_ascii=False))
    print(f"seeded {len(mapping)} chunks for tenant {tenant_id}; wrote resolved gold -> {args.out}")
    print(json.dumps(mapping, indent=2, sort_keys=True))
    return 0


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

    p_gs = sub.add_parser("gold-status", help="SME-review provenance + language mix of a gold set")
    p_gs.add_argument("--gold", default="packages/common/tests/fixtures/gold/failure_modes.json")
    p_gs.add_argument("--require-reviewed", action="store_true", help="exit 1 if any unreviewed")
    p_gs.set_defaults(func=_gold_status)

    p_seed = sub.add_parser("seed", help="seed a real eval corpus + emit resolved gold (5.1/5.2)")
    p_seed.add_argument("--tenant", required=True, help="eval tenant uuid (created if absent)")
    p_seed.add_argument("--gold", default="packages/common/tests/fixtures/gold/failure_modes.json")
    p_seed.add_argument("--out", default="eval-results/failure_modes.resolved.json")
    p_seed.set_defaults(func=_seed)

    p_ragas = sub.add_parser("ragas", help="live Ragas LLM-judged metrics (Story 5.2)")
    p_ragas.add_argument("--gold", required=True)
    p_ragas.add_argument("--tenant", required=True)
    p_ragas.add_argument("--k", type=int, default=5)
    p_ragas.add_argument("--sample", type=int, default=0, help="bounded sample size (0=all)")
    p_ragas.add_argument("--out", default="eval-results")
    p_ragas.set_defaults(func=_ragas)

    p_compare = sub.add_parser("compare", help="custom-vs-Ragas comparison report (Story 5.2)")
    p_compare.add_argument("--gold", required=True)
    p_compare.add_argument("--tenant", required=True)
    p_compare.add_argument("--k", type=int, default=5)
    p_compare.add_argument("--sample", type=int, default=0, help="bounded sample size (0=all)")
    p_compare.add_argument("--runs", type=int, default=1, help="repeat Ragas N× for variance")
    p_compare.add_argument("--out", default="eval-results")
    p_compare.set_defaults(func=_compare)

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
