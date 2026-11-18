"""Generate a BRIDGE-HOP probe — the failure class flat decomposition can't fix (MISSION-054).

The question we want to MEASURE: is there a multi-hop shape the *static* decomposition fan-out
(MISSION-050) structurally cannot answer, that the *cyclic controller* (`--agent`, MISSION-054) can?
The candidate is the **bridge / conditional hop**: hop 2 depends on the *answer* of hop 1.

    A (link):  "The <system> is fitted with the <component>."        <- names the SYSTEM
    B (fact):  "The <component> has a <property> of <value>."         <- names the COMPONENT
    Q:         "What is the <property> of the component fitted to the <system>?"   (names S, not C)

A single retrieval on Q surfaces A (it mentions the system) but NOT uniquely B — because B is keyed
by the *component*, which Q never names. **Distractor facts** (other components sharing the same
property) make the property phrase alone ambiguous, so you cannot pick the right B without first
learning the component from A. That is the bridge:
  - fixed flow     -> one retrieval: gets A, can't disambiguate B -> wrong/abstain;
  - --decompose    -> splits into SELF-CONTAINED parts, but "the <property> of the component?" is
                      unknowable at split time (the component isn't known yet) -> can't form hop 2;
  - --agent        -> step 0 retrieves A, READS the component from the evidence (content-aware
                      observations, MISSION-054), step 1 queries "<component> <property>" -> gets B.

Synthetic + grounded: entities are invented (this measures the MECHANISM, not a natural
distribution — honest caveat, cf. MISSION-049's "grounded, not invented" isolation), but the corpus
is controlled so the bridge is forced, not incidental.

Usage:
  # 1) emit the symbolic gold (deterministic, no DB) for inspection/versioning:
  python scripts/dataset/gen_bridge_probe.py
  # 2) seed the mini-corpus + emit the RESOLVED gold (live — needs DB + Azure embeddings):
  uv run --group embeddings python scripts/dataset/gen_bridge_probe.py --seed \
      --tenant c0f90000-0000-4000-8000-0000000000b1 --out eval-results/ab/bridge_probe.resolved.json
  # 3) run the arms (next mission): eval run --gold <resolved> --tenant <b1> [--decompose|--agent]
"""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from ikip_common.eval.seed import SeedDoc

# A dedicated tenant for the bridge probe (isolated corpus, like NTRS' …a1). …b1 = "bridge".
BRIDGE_TENANT = uuid.UUID("c0f90000-0000-4000-8000-0000000000b1")
_OUT_DIR = Path("eval-results/ab")


@dataclass(frozen=True)
class BridgeSpec:
    """One bridge case: Q names `system` + `prop`; the answer `value` lives in a fact chunk keyed by
    `component`, which Q never names. `distractors` are (other_component, other_value) sharing
    `prop` — they make the property phrase ambiguous so the component must be learned first."""

    key: str
    system: str
    component: str
    prop: str
    value: str
    distractors: tuple[tuple[str, str], ...]


# 6 bridge cases, industrial-flavoured. Component model names are deliberately distinct from system
# names so the link chunk is retrieved by the system and the fact chunk only by the component.
BRIDGE_SPECS: tuple[BridgeSpec, ...] = (
    BridgeSpec(
        "compressor-sensor-temp",
        system="X-200 compressor",
        component="TH-9 temperature sensor",
        prop="maximum operating temperature",
        value="120 °C",
        distractors=(("TH-4 temperature sensor", "85 °C"), ("TH-7 temperature sensor", "150 °C")),
    ),
    BridgeSpec(
        "pump-seal-pressure",
        system="P-44 feed pump",
        component="MS-3 mechanical seal",
        prop="maximum rated pressure",
        value="34 bar",
        distractors=(("MS-1 mechanical seal", "16 bar"), ("MS-8 mechanical seal", "50 bar")),
    ),
    BridgeSpec(
        "turbine-bearing-rpm",
        system="GT-18 gas turbine",
        component="BR-22 journal bearing",
        prop="maximum continuous speed",
        value="9 500 rpm",
        distractors=(
            ("BR-10 journal bearing", "3 600 rpm"),
            ("BR-30 journal bearing", "12 000 rpm"),
        ),
    ),
    BridgeSpec(
        "valve-actuator-torque",
        system="V-7 control valve",
        component="AC-5 pneumatic actuator",
        prop="rated output torque",
        value="220 N·m",
        distractors=(("AC-2 pneumatic actuator", "90 N·m"), ("AC-9 pneumatic actuator", "400 N·m")),
    ),
    BridgeSpec(
        "motor-winding-voltage",
        system="M-12 drive motor",
        component="WD-6 stator winding",
        prop="rated insulation voltage",
        value="690 V",
        distractors=(("WD-2 stator winding", "400 V"), ("WD-11 stator winding", "1 000 V")),
    ),
    BridgeSpec(
        "heatx-tube-flow",
        system="HX-3 heat exchanger",
        component="TB-14 tube bundle",
        prop="maximum design flow rate",
        value="75 m³/h",
        distractors=(("TB-5 tube bundle", "30 m³/h"), ("TB-20 tube bundle", "140 m³/h")),
    ),
)


def _corpus(specs: tuple[BridgeSpec, ...]) -> tuple[SeedDoc, ...]:
    """Expand each spec into its link chunk, its correct fact chunk, and the distractor facts."""
    docs: list[SeedDoc] = []
    for s in specs:
        docs.append(
            SeedDoc(
                f"br-{s.key}-link",
                f"{s.system} configuration",
                f"The {s.system} is fitted with the {s.component}.",
            )
        )
        docs.append(
            SeedDoc(
                f"br-{s.key}-fact",
                f"{s.component} datasheet",
                f"The {s.component} has a {s.prop} of {s.value}.",
            )
        )
        for i, (other, val) in enumerate(s.distractors):
            docs.append(
                SeedDoc(
                    f"br-{s.key}-dist{i}",
                    f"{other} datasheet",
                    f"The {other} has a {s.prop} of {val}.",
                )
            )
    return tuple(docs)


def _gold(specs: tuple[BridgeSpec, ...]) -> dict:
    """The gold: Q names the system + property (never the component); the two chunks that must BOTH
    be retrieved to answer are the link + the correct fact (distractors are NOT relevant)."""
    cases = []
    for s in specs:
        cases.append(
            {
                "case_key": f"br-{s.key}",
                "question": (
                    f"What is the {s.prop} of the component fitted to the {s.system}?"
                ),
                "expected_behavior": "answered",
                "ground_truth": (
                    f"The {s.component} fitted to the {s.system} has a {s.prop} of {s.value}."
                ),
                "language": "en",
                "reviewed": False,
                "category": "bridge_hop",
                # BOTH needed: the link (to learn the component) + the correct fact (the value).
                "relevant_chunk_ids": [f"br-{s.key}-link", f"br-{s.key}-fact"],
            }
        )
    return {"gold_set_version": "ntrs-bridge-2hop-v1", "language": "en", "cases": cases}


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate (and optionally seed) the bridge-hop probe.")
    ap.add_argument("--seed", action="store_true", help="seed the mini-corpus + emit resolved gold")
    ap.add_argument("--tenant", default=str(BRIDGE_TENANT), help="tenant uuid for --seed")
    ap.add_argument(
        "--out",
        default=str(_OUT_DIR / "bridge_probe.json"),
        help="gold output path (resolved when --seed)",
    )
    args = ap.parse_args()

    corpus = _corpus(BRIDGE_SPECS)
    gold = _gold(BRIDGE_SPECS)
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not args.seed:
        # Deterministic, no DB: emit the SYMBOLIC gold for inspection (chunk ids resolve on --seed).
        out = Path(args.out)
        out.write_text(json.dumps(gold, indent=2, ensure_ascii=False))
        print(
            f"{out}: {len(gold['cases'])} bridge cases; corpus = {len(corpus)} chunks "
            f"({len(BRIDGE_SPECS)} link + {len(BRIDGE_SPECS)} fact + "
            f"{len(corpus) - 2 * len(BRIDGE_SPECS)} distractors). Symbolic — run --seed to resolve."
        )
        return

    # Live: seed the corpus through the real indexing path, then resolve the gold's chunk ids.
    from ikip_common.db.session import make_engine
    from ikip_common.eval.seed import resolve_gold_ids, seed_corpus
    from ikip_common.llm import build_embedding_client
    from sqlalchemy.orm import Session

    tenant_id = uuid.UUID(args.tenant)
    with Session(make_engine()) as session:
        mapping = seed_corpus(
            session, tenant_id, build_embedding_client(), corpus=corpus, tenant_name="eval-bridge"
        )
        session.commit()
    resolved = resolve_gold_ids(gold, mapping)
    Path(args.out).write_text(json.dumps(resolved, indent=2, ensure_ascii=False))
    print(f"seeded {len(mapping)} chunks for tenant {tenant_id}; wrote resolved gold -> {args.out}")


if __name__ == "__main__":
    main()
