"""Versioned prompt + model configuration registry (Story 5.5, ADR 0013).

Prompts and the model config that shapes answers are **versioned repo artifacts** under
`prompt_config/` (git is the source of truth): a PR diff is what triggers the regression
gates (AC2), promotion is gated on retrieval + groundedness + safety (AC3), and rollback
is a pointer flip (AC4). On promotion the active version is **synced to Langfuse prompt
management** (label `production`) for the UI + prompt↔trace correlation (AC1) — behind a
port so CI stays deterministic and the SDK is never a hard dependency.

Runtime reads the active artifact (`active_prompt_config()`); a built-in fallback
(`BUILTIN_V1`) keeps the answer flow working even if the artifact dir is missing. v1's
content IS `BUILTIN_V1` (asserted by a test), so the registry can't silently drift from
what the code ships.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from pathlib import Path

_CONFIG_DIR = Path(__file__).parent / "prompt_config"
_ACTIVE_FILE = "active.json"


class PromptConfigError(RuntimeError):
    """Raised when a prompt config version is missing or invalid."""


class PromotionBlockedError(RuntimeError):
    """Raised when a promotion is attempted while a release gate is failing."""


@dataclass(frozen=True)
class ModelConfig:
    """The model knobs a prompt version was tuned for (versioned alongside the prompts)."""

    chat_deployment: str
    reasoning_effort: str
    temperature: float | None


@dataclass(frozen=True)
class PromptConfig:
    version: str
    generate_system: str
    judge_system: str
    not_certified_notice: str
    model: ModelConfig

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, doc: dict) -> PromptConfig:
        try:
            return cls(
                version=doc["version"],
                generate_system=doc["generate_system"],
                judge_system=doc["judge_system"],
                not_certified_notice=doc["not_certified_notice"],
                model=ModelConfig(**doc["model"]),
            )
        except (KeyError, TypeError) as exc:
            raise PromptConfigError(f"invalid prompt config: {exc}") from exc

    def content_hash(self) -> str:
        """Stable hash of the content (version-independent): two versions with identical
        text + model hash the same, so a no-op 'change' is detectable."""
        payload = {k: v for k, v in self.to_dict().items() if k != "version"}
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- built-in v1 (the canonical source of the shipped prompts) -------------

BUILTIN_V1 = PromptConfig(
    version="v1",
    generate_system=(
        "You answer industrial maintenance questions using ONLY the evidence provided. "
        "Each evidence block has a handle like [E1]. Rules:\n"
        "- Ground every claim in the evidence; cite the supporting handles in evidence_markers.\n"
        "- Use ONLY handles shown; never invent a handle or use outside knowledge.\n"
        "- Mark safety_critical=true for hazards, lockout/tagout, injury or "
        "equipment-damage claims.\n"
        "- Put safety warnings / uncertainties from the evidence into warnings.\n"
        "- If the evidence does not answer the question, set status='abstained' with a reason.\n"
        "- Never present output as a certified manufacturer procedure."
    ),
    judge_system=(
        "You are a strict grounding judge. For each claim, decide whether the cited "
        "evidence text ENTAILS it: 'supported' (fully entailed), 'partial' (only partly), "
        "or 'unsupported' (not entailed or evidence missing). Judge only against the "
        "evidence provided; never use outside knowledge. Return one verdict per claim, "
        "in order, by claim_index."
    ),
    not_certified_notice=(
        "This is an AI-generated summary of referenced documentation, not a certified "
        "manufacturer instruction. Verify against the cited source before acting."
    ),
    model=ModelConfig(chat_deployment="gpt-5.4-mini", reasoning_effort="minimal", temperature=None),
)


# --- registry --------------------------------------------------------------


class PromptRegistry:
    """Versioned prompt configs in a directory: `<version>.json` + `active.json`."""

    def __init__(self, root: Path | str = _CONFIG_DIR) -> None:
        self.root = Path(root)

    def versions(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json") if p.name != _ACTIVE_FILE)

    def get(self, version: str) -> PromptConfig:
        path = self.root / f"{version}.json"
        if not path.exists():
            raise PromptConfigError(f"no such prompt config version: {version!r}")
        return PromptConfig.from_dict(json.loads(path.read_text()))

    def active_version(self) -> str:
        path = self.root / _ACTIVE_FILE
        if not path.exists():
            raise PromptConfigError("no active.json in the prompt registry")
        return json.loads(path.read_text())["active"]

    def active(self) -> PromptConfig:
        return self.get(self.active_version())

    def write(self, config: PromptConfig) -> Path:
        """Persist a new (immutable) version artifact."""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{config.version}.json"
        path.write_text(json.dumps(config.to_dict(), indent=2, ensure_ascii=False, sort_keys=True))
        return path

    def activate(self, version: str) -> None:
        """Point `active` at a version. This is how rollback works (AC4): activate the
        prior version — the artifacts are immutable, so it is always reversible."""
        self.get(version)  # validate it exists
        (self.root / _ACTIVE_FILE).write_text(json.dumps({"active": version}, indent=2) + "\n")

    def promote(
        self,
        version: str,
        *,
        gates: GateResult,
        publisher: PromptPublisher | None = None,
        label: str = "production",
    ) -> None:
        """Activate `version` ONLY if all release gates pass (AC3), then sync it to the
        prompt backend (Langfuse) under `label` for the UI + trace correlation (AC1)."""
        if not gates.passed:
            raise PromotionBlockedError(
                f"release gates failing, promotion blocked: {gates.summary()}"
            )
        self.activate(version)
        if publisher is not None:
            publisher.publish(self.get(version), label=label)


def default_registry() -> PromptRegistry:
    return PromptRegistry(_CONFIG_DIR)


@lru_cache(maxsize=1)
def active_prompt_config() -> PromptConfig:
    """The active prompt config for the running process. Falls back to BUILTIN_V1 if the
    artifact dir is missing/unreadable, so the answer flow never breaks on config IO."""
    try:
        return default_registry().active()
    except (PromptConfigError, OSError, ValueError):
        return BUILTIN_V1


# --- release gates (AC3) ---------------------------------------------------


@dataclass(frozen=True)
class GateResult:
    retrieval: bool
    groundedness: bool
    safety: bool
    details: dict

    @property
    def passed(self) -> bool:
        return self.retrieval and self.groundedness and self.safety

    def summary(self) -> str:
        flags = {
            "retrieval": self.retrieval,
            "groundedness": self.groundedness,
            "safety": self.safety,
        }
        return ", ".join(f"{k}={'ok' if v else 'FAIL'}" for k, v in flags.items())


# Minimum aggregate quality a config must clear to be promotable. Deliberately explicit
# (not the regression delta): promotion is an absolute floor on top of the no-regression
# check, so a run can't be promoted just because it didn't regress a weak baseline.
DEFAULT_GATE_THRESHOLDS = {
    "recall_at_k_mean": 0.6,
    "citation_grounding_coverage_mean": 0.9,
    "behavior_conformity": 1.0,
}


def evaluate_gates(
    eval_aggregate: dict | None,
    *,
    safety_passed: bool,
    thresholds: dict | None = None,
) -> GateResult:
    """Combine the eval aggregate (retrieval + groundedness) with the safety gate into a
    single promotion verdict. A missing eval aggregate fails the quality gates (promotion
    requires evidence, it never passes by default)."""
    th = thresholds or DEFAULT_GATE_THRESHOLDS
    agg = eval_aggregate or {}
    retrieval = bool(eval_aggregate) and agg.get("recall_at_k_mean", -1) >= th["recall_at_k_mean"]
    groundedness = (
        bool(eval_aggregate)
        and agg.get("citation_grounding_coverage_mean", -1)
        >= th["citation_grounding_coverage_mean"]
        and agg.get("behavior_conformity", -1) >= th["behavior_conformity"]
    )
    return GateResult(
        retrieval=retrieval,
        groundedness=groundedness,
        safety=bool(safety_passed),
        details={"thresholds": th, "aggregate": agg or None, "safety_passed": bool(safety_passed)},
    )


# --- prompt publishing port (Langfuse sync on promote) ---------------------


class PromptPublisher:
    """Port: publish a prompt config to the prompt-management backend under a label."""

    def publish(self, config: PromptConfig, *, label: str) -> None:  # pragma: no cover - protocol
        raise NotImplementedError


class NullPromptPublisher(PromptPublisher):
    """No-op publisher: git stays the source of truth; Langfuse sync is skipped."""

    def publish(self, config: PromptConfig, *, label: str) -> None:
        return None


class LangfusePromptPublisher(PromptPublisher):
    """Sync each prompt in a config to Langfuse prompt management (lazy SDK import).

    Each prompt becomes a named Langfuse prompt (`ikip/generate-system`, …) labelled
    `production`, carrying the config version + model params so the UI shows what the
    running answer flow uses and traces (Story 5.4) can link back to it.
    """

    _NAMES = {
        "generate_system": "ikip/generate-system",
        "judge_system": "ikip/judge-system",
        "not_certified_notice": "ikip/not-certified-notice",
    }

    def __init__(self, settings=None) -> None:  # noqa: ANN001
        # Import the SDK eagerly so a missing optional dependency surfaces here as
        # ImportError and `build_prompt_publisher` can fall back to a no-op.
        from langfuse import Langfuse

        from ikip_common.config import get_settings

        self._Langfuse = Langfuse
        self._settings = settings or get_settings()

    def publish(self, config: PromptConfig, *, label: str) -> None:
        s = self._settings
        client = self._Langfuse(
            public_key=s.langfuse_public_key.get_secret_value(),
            secret_key=s.langfuse_secret_key.get_secret_value(),
            host=s.langfuse_host,
        )
        shared = {"version": config.version, "model": config.model.__dict__}
        for field, name in self._NAMES.items():
            client.create_prompt(
                name=name,
                prompt=getattr(config, field),
                labels=[label],
                config=shared,
                type="text",
            )


def build_prompt_publisher(settings=None) -> PromptPublisher:  # noqa: ANN001
    """Langfuse publisher when credentials + SDK are available, else a no-op (so promote
    works offline and in CI; git remains the source of truth)."""
    from ikip_common.config import get_settings

    s = settings or get_settings()
    if s.langfuse_public_key is None or s.langfuse_secret_key is None:
        return NullPromptPublisher()
    try:
        return LangfusePromptPublisher(s)
    except ImportError:
        return NullPromptPublisher()


def _builtin_variant(version: str, **changes: object) -> PromptConfig:
    """Helper for tests/tools: a new version derived from BUILTIN_V1."""
    return replace(BUILTIN_V1, version=version, **changes)
