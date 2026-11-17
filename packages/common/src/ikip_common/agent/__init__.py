"""Agentic request-time layer (ADR 0033 / Epic 10) — Tool port + registry + cyclic controller.

Built *alongside* the fixed grounded-answer flow (ADR 0022), on the same LangGraph + ports
(ADR 0021), enabled per query by a router. Nothing here weakens the grounding guarantee: tools
carry provenance, the controller is bounded by deterministic guardrails, and the existing
validator/abstention still decide the final answer.
"""
