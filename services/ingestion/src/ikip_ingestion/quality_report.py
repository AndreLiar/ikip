"""Data-quality report (Story 2.6 AC2). Pure — summarizes a pipeline run.

Aggregates per-run outcomes (successes, failures, duplicates, dead-letters) into
a structured report that can be logged, surfaced in the Dagster UI, and stored.
Computed from ingestion-job states + dedup results, so it never queries anything
itself — the Dagster step feeds it the counts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class DataQualityReport:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    dead_letter: int = 0
    duplicates: int = 0  # exact-dup documents skipped
    new_documents: int = 0
    new_versions: int = 0
    low_quality_docs: list[str] = field(default_factory=list)  # job/source ids

    @property
    def success_rate(self) -> float:
        return round(self.succeeded / self.total, 4) if self.total else 0.0

    @property
    def failure_rate(self) -> float:
        failures = self.failed + self.dead_letter
        return round(failures / self.total, 4) if self.total else 0.0

    def as_dict(self) -> dict:
        d = asdict(self)
        d["success_rate"] = self.success_rate
        d["failure_rate"] = self.failure_rate
        return d
