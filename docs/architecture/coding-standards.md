# Coding Standards

_Sharded from `../architecture.md`. Part of the [architecture index](./index.md)._

- Python: type hints + Pydantic models at boundaries; ruff/black; services depend on interfaces from `packages/common`, never on Azure SDKs directly. — enforces [ADR 0003](../adr/0003-local-first-ports-and-adapters.md).
- TypeScript: strict mode; shared API types generated from OpenAPI where possible.
- Tenant scoping is enforced in the repository layer — no raw cross-tenant queries.
- ADRs recorded for significant decisions — see [`../adr/README.md`](../adr/README.md).
- Retrieved document content is always treated as untrusted (prompt-injection posture).
