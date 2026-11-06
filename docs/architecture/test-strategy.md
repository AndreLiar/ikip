# Test Strategy

_Sharded from `../architecture.md`. Part of the [architecture index](./index.md)._

Full pyramid + specialized suites (mirrors `tests/`):

- **Unit** — logic, repositories (incl. tenant scoping).
- **Integration** — API + DB + storage + queue.
- **Retrieval** — Recall@K, ranking, citation resolution on gold datasets (regression-gated).
- **Security** — tenant isolation (zero cross-tenant disclosure), authorize-before-retrieve, prompt-injection/malicious-document.
- **Safety** — 100% pass on critical safety-abstention set (release-blocking).
- **Performance** — p95 retrieval < 1.5 s, p95 TTFT < 5 s under defined load (k6).

CI enforces all gates before deploy (NFR14). Specialized suites are driven by Epic 5 (evaluation) and Epic 6 (security/safety).
