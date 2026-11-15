"""Per-corpus faithfulness regression gate (ADR 0016).

`faithfulness` = fraction of answer claims supported by the retrieved evidence = the hallucination
meter. This gate asserts that a corpus's **measured** faithfulness (from a Ragas run) stays at or
above a **per-corpus floor** (committed, versioned). A prompt/model/retrieval change that silently
lowers faithfulness on any corpus fails the gate.

Pure + deterministic (no network): the expensive Ragas measurement is separate; this just compares
a produced number to the floor. Floors are keyed by `gold_set_version` so each corpus has its own.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Floors:
    default: float
    by_version: dict[str, float]

    def floor_for(self, version: str) -> float:
        return self.by_version.get(version, self.default)


@dataclass(frozen=True)
class GateResult:
    version: str
    faithfulness: float
    floor: float

    @property
    def passed(self) -> bool:
        return self.faithfulness >= self.floor

    def __str__(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        return (
            f"[{verdict}] faithfulness gate: {self.version} "
            f"faithfulness={self.faithfulness:.3f} floor={self.floor:.3f}"
        )


def load_floors(path: str | Path) -> Floors:
    doc = json.loads(Path(path).read_text())
    return Floors(default=float(doc.get("default", 0.0)), by_version=dict(doc.get("floors", {})))


def check_faithfulness(version: str, faithfulness: float, floors: Floors) -> GateResult:
    """Compare a corpus's measured faithfulness to its per-version floor."""
    return GateResult(version=version, faithfulness=faithfulness, floor=floors.floor_for(version))
