# Source Tree

_Sharded from `../architecture.md`. Part of the [architecture index](./index.md)._

```
ikip/
├── apps/
│   ├── web/                  # Next.js frontend
│   └── api/                  # FastAPI backend
├── services/
│   ├── ingestion/
│   ├── document-processing/
│   ├── indexing/
│   ├── retrieval/
│   └── evaluation/
├── packages/
│   ├── common/               # shared models, interfaces, tenant utils
│   └── ai-clients/           # pluggable LLM/embedding adapters
├── infrastructure/
│   ├── docker/compose.yaml
│   └── terraform/{modules,environments/{dev,staging,prod}}
├── tests/{unit,integration,retrieval,security,performance}
├── datasets/evaluation/
├── .github/workflows/
└── docs/
```

> Monorepo rationale: [ADR 0006](../adr/0006-monorepo.md).
