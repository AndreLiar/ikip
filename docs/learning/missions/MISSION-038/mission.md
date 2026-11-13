# MISSION-038 — Prompt-Injection & Malicious-Document Defenses (Epic 6, Story 6.3)

**Mode:** Autonome (hardens + observes an existing guardrail) + knowledge transfer.
**Objective:** treat retrieved content as untrusted, block/neutralize adversarial injection, and **log + surface** the attempts — as a required CI gate.
**Maps to:** Epic 6 / Story 6.3. Closes threat **T5**; builds on the safety gate (5.3) and the live poisoned-doc finding.

## The defense model (two structural + one observability layer)
1. **No tools (AC1).** The `ChatClient` port exposes only `complete_structured` — **no function-calling / tool access**. The model can emit claims, never *act*. An injected "do X" instruction has no execution surface.
2. **Server-side citations + grounding (AC1/AC2).** The model sees opaque evidence handles; citations resolve server-side; an unsupported safety-critical claim (what an injection produces) forces **abstention**. This already neutralizes the outcome (proven in 5.3 + `test_answer_graph.py`).
3. **Detection + logging + surfacing (AC3) — new.** `ikip_common/llm/injection.py`: `detect_injection(text)` / `scan_evidence(evidence)` flag known injection/jailbreak patterns (instruction-override, exfiltration, role-reassign). The answer graph scans retrieved evidence, **logs** a security WARNING (pattern names only — never the raw malicious text), and the result **surfaces** a fixed warning (`INJECTION_WARNING`) to the caller/UI. Pure/deterministic → runs in the fast gate.

## What was built
- `llm/injection.py` — curated regex patterns + `detect_injection` / `scan_evidence` (returns pattern *names*, never echoes the payload).
- `llm/answer.py` — `retrieve_node` scans evidence, logs on a hit, flags state; `grounded_answer` appends `INJECTION_WARNING` to `result.warnings` (surfaced regardless of answered/abstained).
- Tests `packages/common/tests/test_injection.py` — pattern detection, benign content clean, no-raw-echo, the safety fixtures are flagged, and an **end-to-end**: a poisoned doc → detected + logged + warning surfaced + the unsafe instruction **not followed** (abstained).
- CI: the injection suite is added to the **required `safety-gate` job** (AC4); it also runs in `validate`.
- Threat model T5 updated to `[implemented: 5.3 + 6.3]`.

## Acceptance (Story 6.3)
1. Retrieved content treated as untrusted; tool access restricted. — **[verified]** (no-tools port + scan-as-data; documented in the threat model).
2. Adversarial injection / hostile instructions blocked/neutralized. — **[verified]** (grounding abstains; end-to-end test; safety suite malicious-doc cases).
3. Failures logged and surfaced. — **[verified]** (WARNING log with pattern names; `INJECTION_WARNING` in the answer; caplog asserts the log).
4. Tests run in CI as a required gate. — **[verified]** (`safety-gate` runs `test_injection.py`; also in `validate`).

## Verification
- ruff + format ✓; `pytest apps packages services` → **257 passed / 48 skipped**; injection suite 10 tests (pure + langgraph).

## Deliverables
- `packages/common/src/ikip_common/llm/injection.py`; wiring in `llm/answer.py`.
- `packages/common/tests/test_injection.py`; `ci.yml` (`safety-gate` step); threat-model T5 update.

## Follow-ups (noted)
- The judge-fooling residual (a poisoned doc the grounding judge wrongly calls "supported") is defended upstream by **document provenance/trust** (Story 6.5) — don't retrieve untrusted content into the model.
- A metric (`ikip_security_events_total{event="injection"}`) on the Ops dashboard would trend attempts (small follow-up to 5.6).

## Concepts
Extends [grounded-answers](../../concepts/grounded-answers.md); realises threat **T5** of the [threat model](../../architecture/threat-model.md). Builds on [[MISSION-027]] (safety gate) + [[MISSION-037]] (threat model).
