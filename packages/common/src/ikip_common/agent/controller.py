"""Cyclic plan–act–observe controller + guardrails (ADR 0033 / Story 10.2).

This is what makes the pipeline *agentic*: instead of the engineer wiring the steps (the fixed
flow), a **policy** decides each step — *plan a step → act (call a tool) → observe the result →
loop or stop*. The policy is a port: `LlmControllerPolicy` asks the model (prod); `ScriptedPolicy`
replays a fixed plan (tests) — so the loop + every guardrail are tested with no LLM/DB.

**Guardrails are deterministic and non-negotiable**, because a loop + an LLM can otherwise run away
in cost or spin forever. Termination never depends on the model:
- `max_steps` — a hard cap on iterations;
- **loop / no-progress detection** — the same `(tool, args)` twice, or a step that adds no new
  evidence, stops the run;
- **cost budget** — an injected `cost_fn` accumulates per-step cost; crossing `max_cost_usd` stops;
- **kill-switch** — a per-run flag refuses to start (operator/tenant off-switch).

The controller only *gathers evidence*; it does **not** write the answer. Its `AgentTrajectory`
(evidence + the step log) is handed to the **existing** generate/validate nodes, so grounding,
citations and abstention are unchanged (ADR 0022) — the agent changes *what we retrieve*, never
*what we claim*. The trajectory is the audit trail (trace per step, Story 10.7).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from ikip_common.agent.tools import ToolEvidence, ToolRegistry, ToolResult


class _ControllerDecision(BaseModel):
    """Structured controller output. `tool=None` means stop; `query` is the retrieval tool's input.

    `query` is a flat string (not an open `dict`) on purpose: OpenAI/Azure structured output rejects
    free-form object properties (`additionalProperties` must be false), so an open `args` dict makes
    every decision call fail. Every current tool takes `{"query": str}`; the policy rebuilds that
    dict from `query`. A non-`query` tool would add its own typed field here."""

    tool: str | None = None
    query: str = ""
    reason: str = ""


@dataclass(frozen=True)
class AgentAction:
    """A controller decision: call `tool` with `args`, or **stop** when `tool is None`."""

    tool: str | None
    args: dict = field(default_factory=dict)
    reason: str = ""

    @property
    def is_stop(self) -> bool:
        return self.tool is None


@dataclass
class AgentStep:
    """One act→observe record: the action taken and what the tool returned (None if it errored)."""

    action: AgentAction
    result: ToolResult | None


@dataclass
class AgentTrajectory:
    """The full run: ordered steps, the de-duplicated evidence gathered, and why it stopped.
    `stop_reason` ∈ {stop, max_steps, loop, no_progress, budget, kill_switch, error}."""

    steps: list[AgentStep]
    evidence: list[ToolEvidence]
    stop_reason: str


@dataclass(frozen=True)
class AgentBudget:
    """Deterministic bounds. Defaults are conservative (a hard tail is usually 2–4 steps)."""

    max_steps: int = 4
    max_cost_usd: float = 0.0  # 0 = no cost cap
    kill_switch: bool = False


@runtime_checkable
class ControllerPolicy(Protocol):
    """Decides the next step given the question, the tool menu, and what's been observed so far."""

    def decide(
        self, *, question: str, tools_menu: str, observations: str, step: int
    ) -> AgentAction: ...


# A bridge/conditional hop needs the policy to read *what* a prior step found (an entity) to form
# the next query — not just how many passages it got. So the observation history carries a bounded
# snippet of each step's evidence content. Bounds keep the controller prompt cost/size predictable.
_OBS_MAX_PASSAGES = 3  # per step, how many passage snippets to surface
_OBS_SNIPPET_CHARS = 240  # per passage, truncate content


def _observations(steps: Sequence[AgentStep]) -> str:
    """Render the act→observe history for the policy prompt (compact + stable). Each step shows the
    call, the passage count, and a bounded snippet of the top passages' *content* — so the policy
    can use an entity found in an earlier step to form a dependent follow-up query (bridge hop)."""
    lines = []
    for i, s in enumerate(steps):
        ev = [] if s.result is None else s.result.evidence
        args = json.dumps(s.action.args, sort_keys=True)
        lines.append(f"[{i}] {s.action.tool}({args}) -> {len(ev)} passages")
        for e in ev[:_OBS_MAX_PASSAGES]:
            snippet = " ".join(e.content.split())[:_OBS_SNIPPET_CHARS]
            cid = e.provenance.get("chunk_id", "?")
            lines.append(f"      - [{cid}] {snippet}")
    return "\n".join(lines)


def run_agent(
    *,
    question: str,
    registry: ToolRegistry,
    policy: ControllerPolicy,
    budget: AgentBudget | None = None,
    cost_fn: Callable[[AgentAction, ToolResult | None], float] = lambda _a, _r: 0.0,
) -> AgentTrajectory:
    """Run the plan–act–observe loop under the guardrails. Returns the evidence + step log; never
    the answer (that stays with generate/validate). Pure given a `ScriptedPolicy` + fake tools."""
    budget = budget or AgentBudget()
    steps: list[AgentStep] = []
    evidence: list[ToolEvidence] = []
    seen_actions: set[tuple[str, str]] = set()
    seen_chunks: set[object] = set()
    cost = 0.0

    if budget.kill_switch:
        return AgentTrajectory(steps, evidence, "kill_switch")

    for i in range(budget.max_steps):
        action = policy.decide(
            question=question,
            tools_menu=registry.describe(),
            observations=_observations(steps),
            step=i,
        )
        if action.is_stop:
            return AgentTrajectory(steps, evidence, "stop")

        key = (action.tool or "", json.dumps(action.args, sort_keys=True))
        if key in seen_actions:  # loop guard: the same call twice makes no progress
            return AgentTrajectory(steps, evidence, "loop")
        seen_actions.add(key)

        try:
            tool = registry.get(action.tool)  # type: ignore[arg-type]
        except KeyError:  # the policy named a tool that doesn't exist
            steps.append(AgentStep(action, None))
            return AgentTrajectory(steps, evidence, "error")

        result = tool.invoke(action.args)
        steps.append(AgentStep(action, result))
        cost += cost_fn(action, result)

        new = [e for e in result.evidence if e.provenance.get("chunk_id") not in seen_chunks]
        for e in new:
            seen_chunks.add(e.provenance.get("chunk_id"))
        evidence.extend(new)

        if budget.max_cost_usd and cost > budget.max_cost_usd:
            return AgentTrajectory(steps, evidence, "budget")
        if not new:  # a step that surfaced nothing new → no progress
            return AgentTrajectory(steps, evidence, "no_progress")

    return AgentTrajectory(steps, evidence, "max_steps")


class ScriptedPolicy:
    """Replays a fixed list of `AgentAction`s (then stops) — deterministic loop/guardrail tests."""

    def __init__(self, actions: Sequence[AgentAction]) -> None:
        self._actions = list(actions)

    def decide(
        self, *, question: str, tools_menu: str, observations: str, step: int
    ) -> AgentAction:  # noqa: ARG002
        if step < len(self._actions):
            return self._actions[step]
        return AgentAction(tool=None, reason="done")


class LlmControllerPolicy:
    """Production policy: the model picks the next tool (or stops), given the question, the tool
    menu and the observation history. Uses the `ChatClient` port (FakeChatClient in CI), so the
    agent decision is one structured LLM call — bounded by the same guardrails. On any error it
    returns a **stop** (fail-safe: the loop degrades to whatever evidence it already has, never a
    crash or an un-grounded guess)."""

    def __init__(self, chat_client, *, system: str | None = None) -> None:  # noqa: ANN001 — ChatClient port
        self._chat = chat_client
        self._system = system or _CONTROLLER_SYSTEM

    def decide(
        self, *, question: str, tools_menu: str, observations: str, step: int
    ) -> AgentAction:
        from ikip_common.llm.base import ChatMessage

        prompt = (
            f"Question:\n{question}\n\nTools:\n{tools_menu}\n\n"
            f"Observations so far (step {step}):\n{observations or '(none yet)'}\n\n"
            "Pick the next tool to gather missing evidence, or stop if you have enough. "
            'Reply with the tool name + the search query string, or tool=null to stop.'
        )
        try:
            out = self._chat.complete_structured(
                [
                    ChatMessage(role="system", content=self._system),
                    ChatMessage(role="user", content=prompt),
                ],
                _ControllerDecision,
            )
            args = {"query": out.query} if out.query else {}
            return AgentAction(tool=out.tool or None, args=args, reason=out.reason or "")
        except Exception:  # noqa: BLE001 — a controller failure must stop, never crash the request
            return AgentAction(tool=None, reason="policy_error")


_CONTROLLER_SYSTEM = (
    "You are a retrieval controller for a grounded Q&A system. You do NOT answer the question; you "
    "only decide which retrieval tool to call next to gather citable evidence, one step at a time. "
    "Prefer the fewest steps; call a tool only when it would add missing evidence; stop as soon as "
    "the gathered evidence covers every part of the question. Never invent facts. "
    "If the question asks about something that is only identified by a prior step's result (a "
    "bridge/conditional hop), read the entity you found in the observations and use it to form the "
    "next query — do not re-query the same thing."
)
