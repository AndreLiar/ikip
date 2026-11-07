"""Evaluation report I/O (Story 3.6). Three distinct artifacts so a bad run never
silently becomes the reference:

  runs/<timestamp>.json  — immutable history (one per run)
  latest.json            — the most recent run (convenience pointer)
  baseline.json          — the APPROVED reference; only set by explicit `promote`

`write_run` writes runs/ + latest, never baseline. Regression checks compare a run to
`baseline.json` (see harness.compare_to_baseline). Pure stdlib → unit-testable.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from ikip_common.eval.harness import EvalReport


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def build_document(report: EvalReport) -> dict:
    """Serialize a report with run metadata (timestamp, dataset version, commit SHA)."""
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "commit_sha": _git_sha(),
        "gold_set_version": report.gold_set_version,
        "config": report.config,
        "aggregate": report.aggregate,
        "cases": report.cases,
    }


def write_run(report: EvalReport, out_dir: str | Path) -> tuple[Path, Path]:
    """Write runs/<timestamp>.json + latest.json. Never touches baseline.json."""
    out = Path(out_dir)
    (out / "runs").mkdir(parents=True, exist_ok=True)
    doc = build_document(report)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_path = out / "runs" / f"{stamp}.json"
    latest_path = out / "latest.json"
    payload = json.dumps(doc, indent=2, sort_keys=True)
    run_path.write_text(payload)
    latest_path.write_text(payload)
    return run_path, latest_path


def load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def promote(out_dir: str | Path) -> Path:
    """Promote latest.json → baseline.json (explicit approval of a new reference)."""
    out = Path(out_dir)
    baseline = out / "baseline.json"
    baseline.write_text((out / "latest.json").read_text())
    return baseline
