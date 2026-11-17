"""Tool port + registry (ADR 0033 / Story 10.1).

A **Tool** is a typed capability the agent can call: "retrieve over corpus X", "look up a spec in
the structured DB", "convert units". Exposing them behind **one port** lets the controller call any
of them uniformly and lets us add/remove capabilities without touching the orchestration.

Two guarantees are **baked into the port, not left to the caller** — because the agent takes more
steps than the fixed flow, and each step is a chance to lose grounding or cross a tenant:

1. **Provenance travels with every result** (`ToolEvidence.provenance`) — the citation chain
   (chunk/doc/version/page, FR16) is a *field on the result*, not reconstructed later, so a merge or
   an extra step can never strip it.
2. **A tool is tenant-scoped by construction** — a retrieval tool is built *for one tenant*; its
   `invoke` can only ever reach that tenant's data (NFR10). Isolation is structural — not a
   check that can be forgotten.

Base-env safe: no langchain/DB import here. A `RetrievalTool` wraps an already-built `retrieve`
callable (e.g. from `make_hybrid_retrieve`), so the heavy deps live in the *injected* function, and
the port + registry are unit-testable with `FakeTool` (no network/DB).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolEvidence:
    """One retrieved passage + its citation. `provenance` mirrors `Document.metadata` (chunk_id,
    document_id, document_version_id, revision, page_start/end, …) so the existing citation
    resolution + grounding validator work unchanged on tool output."""

    content: str
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    """What a tool returns. `evidence` is retrieved, citable passages (the grounding path);
    `abstained` is the tool's "insufficient evidence" signal (preserves the abstention contract).
    `value` is for non-retrieval tools (a computed number/string) — still never an *uncited claim*:
    a value is a tool observation the controller reasons over, not a claim asserted to the user."""

    tool: str
    evidence: list[ToolEvidence] = field(default_factory=list)
    abstained: bool = False
    reason: str | None = None
    value: Any | None = None


@runtime_checkable
class Tool(Protocol):
    """The port. `name` identifies it; `description` is what the controller reads to decide *when*
    to use it (so it must be written for the model); `invoke` runs it. `args` is a plain dict keyed
    per the tool (documented in `description`) — kept simple + serialisable for tracing/replay."""

    name: str
    description: str

    def invoke(self, args: dict[str, Any]) -> ToolResult: ...


class RetrievalTool:
    """A corpus/tenant exposed as a retrieval tool (Story 10.1 AC1). Wraps a `retrieve(query) ->
    RetrievalOutcome` callable (built elsewhere via `make_hybrid_retrieve`, tenant-scoped +
    filtered), so this class stays base-env safe and the tenant binding is **fixed at construction**
    — `invoke` cannot be pointed at another tenant. `args = {"query": str}`."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        retrieve: Callable[[str], Any],  # Callable[[str], RetrievalOutcome]
    ) -> None:
        self.name = name
        self.description = description
        self._retrieve = retrieve

    def invoke(self, args: dict[str, Any]) -> ToolResult:
        query = (args or {}).get("query", "")
        if not isinstance(query, str) or not query.strip():
            return ToolResult(tool=self.name, abstained=True, reason="empty query")
        outcome = self._retrieve(query)
        evidence = [
            ToolEvidence(content=doc.page_content, provenance=dict(doc.metadata))
            for doc in getattr(outcome, "documents", [])
        ]
        return ToolResult(
            tool=self.name,
            evidence=evidence,
            abstained=bool(getattr(outcome, "abstained", not evidence)),
            reason=getattr(outcome, "reason", None),
        )


class FakeTool:
    """Scripted tool for tests — returns a canned `ToolResult` (or records the args it saw), so the
    registry + controller are testable with no DB/LLM/network."""

    def __init__(
        self,
        *,
        name: str = "fake",
        description: str = "a fake tool",
        result: ToolResult | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self._result = result
        self.calls: list[dict[str, Any]] = []

    def invoke(self, args: dict[str, Any]) -> ToolResult:
        self.calls.append(dict(args or {}))
        return self._result or ToolResult(tool=self.name)


class ToolRegistry:
    """A `name -> Tool` map. Config-driven (Story 10.1 AC4): wire a new corpus by registering a
    tool, no orchestration change. `describe()` renders the tool menu for the controller prompt."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def describe(self) -> str:
        """One `- name: description` line per tool, stable order — for the controller's prompt."""
        return "\n".join(f"- {n}: {self._tools[n].description}" for n in self.names())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools
