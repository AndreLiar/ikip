# Source Tree

_Sharded from `../architecture.md`. Part of the [architecture index](./index.md)._

```
ikip/
├── apps/
│   ├── web/                  # Next.js frontend
│   └── api/                  # FastAPI backend (ikip_api)
├── services/
│   ├── ingestion/            # Dagster ingestion pipeline (ikip_ingestion)
│   ├── document-processing/  # extract / OCR / quality / routing (ikip_docproc)
│   ├── indexing/
│   ├── retrieval/
│   └── evaluation/
├── packages/
│   ├── common/               # shared models, ports, tenant utils, agent, eval, llm (ikip_common)
│   └── ai-clients/           # pluggable LLM/embedding adapters
├── infrastructure/
│   ├── docker/docker-compose.yml
│   └── terraform/{modules,environments/{dev,staging,prod}}
├── scripts/                  # dev + dataset utilities (scripts/dataset/* generators, fetchers)
├── grafana/                  # observability config: dashboards/ + alerts/ (Grafana Cloud, MISSION-035)
├── load/k6/                  # load / performance scripts (k6)
├── datasets/evaluation/      # eval corpora (outputs git-ignored; dir held by .gitkeep)
├── tests/{unit,integration,retrieval,security,performance}
├── .github/workflows/
└── docs/
```

> **Where the tests actually live:** unit + integration tests are **co-located** with their code
> (`packages/*/tests/`, `apps/*/tests/`) — that is the authoritative location run by CI. The root
> `tests/{…}` tree reserves categories for cross-cutting / root-level suites; several are still
> `.gitkeep` placeholders (nothing to clean — they mark the intended home for future root-level tests).
>
> **Build/cache dirs** (`.venv/`, `node_modules/`, `.pnpm-store/`, `.pytest_cache/`, `.ruff_cache/`,
> `eval-results/`) are git-ignored and never committed — they are local-only.
>
> Monorepo rationale: [ADR 0006](../adr/0006-monorepo.md). uv workspace members are declared in
> `pyproject.toml` (`[tool.uv.workspace]`); pnpm members in `pnpm-workspace.yaml`.
