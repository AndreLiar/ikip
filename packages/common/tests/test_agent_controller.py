"""Cyclic controller + guardrails tests (ADR 0033 / Story 10.2). Pure — scripted policy + fakes."""

from ikip_common.agent.controller import (
    AgentAction,
    AgentBudget,
    ControllerPolicy,
    LlmControllerPolicy,
    ScriptedPolicy,
    run_agent,
)
from ikip_common.agent.tools import FakeTool, ToolEvidence, ToolRegistry, ToolResult


def _ev(cid: str) -> ToolEvidence:
    return ToolEvidence(content=f"passage {cid}", provenance={"chunk_id": cid})


def _registry(**results: ToolResult) -> ToolRegistry:
    reg = ToolRegistry()
    for name, res in results.items():
        reg.register(FakeTool(name=name, description=f"tool {name}", result=res))
    return reg


# --- happy path --------------------------------------------------------------------------


def test_gathers_evidence_across_steps_and_dedups() -> None:
    reg = _registry(
        a=ToolResult(tool="a", evidence=[_ev("c1"), _ev("c2")]),
        b=ToolResult(tool="b", evidence=[_ev("c2"), _ev("c3")]),  # c2 overlaps -> deduped
    )
    policy = ScriptedPolicy([AgentAction("a", {"query": "x"}), AgentAction("b", {"query": "y"})])
    traj = run_agent(question="q", registry=reg, policy=policy, budget=AgentBudget(max_steps=4))
    assert traj.stop_reason == "stop"  # scripted policy runs out -> stop
    assert [e.provenance["chunk_id"] for e in traj.evidence] == ["c1", "c2", "c3"]  # union, deduped
    assert len(traj.steps) == 2


def test_policy_stop_action_ends_the_run() -> None:
    reg = _registry(a=ToolResult(tool="a", evidence=[_ev("c1")]))
    policy = ScriptedPolicy([AgentAction("a", {"query": "x"}), AgentAction(tool=None)])
    traj = run_agent(question="q", registry=reg, policy=policy)
    assert traj.stop_reason == "stop"
    assert len(traj.evidence) == 1


# --- guardrails --------------------------------------------------------------------------


def test_max_steps_caps_the_loop() -> None:
    # every step returns a NEW chunk, so only max_steps stops it
    reg = ToolRegistry()
    reg.register(FakeTool(name="a", description="a"))

    class _Fresh(ControllerPolicy):  # a policy that always calls "a" with a new arg
        def decide(self, *, question, tools_menu, observations, step):  # noqa: ANN001, ANN201, ARG002
            return AgentAction("a", {"query": f"q{step}"})

    # FakeTool returns the same empty result -> no new evidence -> would be no_progress first;
    # use a tool that yields a fresh chunk per call instead:
    reg = ToolRegistry()

    class _FreshTool:
        name, description = "a", "a"

        def __init__(self):  # noqa: ANN204
            self.n = 0

        def invoke(self, args):  # noqa: ANN001, ANN201, ARG002
            self.n += 1
            return ToolResult(tool="a", evidence=[_ev(f"c{self.n}")])

    reg.register(_FreshTool())
    traj = run_agent(question="q", registry=reg, policy=_Fresh(), budget=AgentBudget(max_steps=3))
    assert traj.stop_reason == "max_steps"
    assert len(traj.steps) == 3


def test_loop_guard_stops_on_repeated_action() -> None:
    reg = _registry(a=ToolResult(tool="a", evidence=[_ev("c1")]))
    policy = ScriptedPolicy([AgentAction("a", {"query": "x"}), AgentAction("a", {"query": "x"})])
    traj = run_agent(question="q", registry=reg, policy=policy, budget=AgentBudget(max_steps=5))
    assert traj.stop_reason == "loop"
    assert len(traj.steps) == 1  # the repeat is detected before a 2nd invoke


def test_no_progress_stops_when_a_step_adds_nothing() -> None:
    reg = _registry(a=ToolResult(tool="a", evidence=[]))  # abstains / empty
    policy = ScriptedPolicy([AgentAction("a", {"query": "x"})])
    traj = run_agent(question="q", registry=reg, policy=policy, budget=AgentBudget(max_steps=5))
    assert traj.stop_reason == "no_progress"


def test_cost_budget_stops_the_run() -> None:
    reg = ToolRegistry()

    class _FreshTool:
        name, description = "a", "a"

        def __init__(self):  # noqa: ANN204
            self.n = 0

        def invoke(self, args):  # noqa: ANN001, ANN201, ARG002
            self.n += 1
            return ToolResult(tool="a", evidence=[_ev(f"c{self.n}")])

    reg.register(_FreshTool())

    class _Fresh(ControllerPolicy):
        def decide(self, *, question, tools_menu, observations, step):  # noqa: ANN001, ANN201, ARG002
            return AgentAction("a", {"query": f"q{step}"})

    traj = run_agent(
        question="q",
        registry=reg,
        policy=_Fresh(),
        budget=AgentBudget(max_steps=10, max_cost_usd=0.25),
        cost_fn=lambda _a, _r: 0.1,  # 0.1/step -> crosses 0.25 on the 3rd
    )
    assert traj.stop_reason == "budget"
    assert len(traj.steps) == 3


def test_kill_switch_refuses_to_start() -> None:
    reg = _registry(a=ToolResult(tool="a", evidence=[_ev("c1")]))
    policy = ScriptedPolicy([AgentAction("a", {"query": "x"})])
    traj = run_agent(
        question="q", registry=reg, policy=policy, budget=AgentBudget(kill_switch=True)
    )
    assert traj.stop_reason == "kill_switch"
    assert traj.steps == [] and traj.evidence == []


def test_unknown_tool_name_errors_safely() -> None:
    reg = _registry(a=ToolResult(tool="a", evidence=[_ev("c1")]))
    policy = ScriptedPolicy([AgentAction("ghost", {"query": "x"})])  # hallucinated tool
    traj = run_agent(question="q", registry=reg, policy=policy)
    assert traj.stop_reason == "error"
    assert traj.steps[-1].result is None  # recorded, no crash


# --- LLM policy (fake chat client) -------------------------------------------------------


class _FakeChat:
    def __init__(self, out) -> None:  # noqa: ANN001
        self._out = out

    @property
    def model_version(self) -> str:
        return "fake"

    def complete_structured(self, messages, schema):  # noqa: ANN001, ANN201, ARG002
        if isinstance(self._out, Exception):
            raise self._out
        return schema(**self._out)


def test_llm_policy_parses_a_tool_call() -> None:
    policy = LlmControllerPolicy(_FakeChat({"tool": "manuals", "args": {"query": "torque?"}}))
    action = policy.decide(question="q", tools_menu="- manuals: x", observations="", step=0)
    assert action.tool == "manuals" and action.args == {"query": "torque?"}


def test_llm_policy_stops_on_null_tool() -> None:
    policy = LlmControllerPolicy(_FakeChat({"tool": None, "reason": "enough"}))
    assert policy.decide(question="q", tools_menu="", observations="", step=1).is_stop


def test_llm_policy_fails_safe_to_stop_on_error() -> None:
    # A controller failure must stop (degrade to gathered evidence), never crash the request.
    policy = LlmControllerPolicy(_FakeChat(RuntimeError("llm down")))
    action = policy.decide(question="q", tools_menu="", observations="", step=0)
    assert action.is_stop and action.reason == "policy_error"
