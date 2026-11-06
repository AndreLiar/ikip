# IKIP System Design Diagrams (diagram-as-code)

Architecture diagrams generated with Python using the [`diagrams`](https://diagrams.mingrammer.com/) library (Graphviz under the hood) — the approach from [freeCodeCamp: *How to Create System Design Diagrams using Python*](https://www.freecodecamp.org/news/how-to-create-system-design-diagrams-using-python/).

Source is code → diagrams stay in sync with the architecture and are reviewable in PRs. Rendered output (committed) lives in [`../img/`](../img).

## Diagrams

| # | Source | Output | Matches |
|---|--------|--------|---------|
| 1 | `01_system_context.py` | `../img/01_system_context.*` | `../high-level-architecture.md` |
| 2 | `02_ingestion_pipeline.py` | `../img/02_ingestion_pipeline.*` | Epic 2 · `../core-workflows.md` |
| 3 | `03_rag_workflow.py` | `../img/03_rag_workflow.*` | Epic 3 · `../core-workflows.md` |
| 4 | `04_azure_deployment.py` | `../img/04_azure_deployment.*` | Epic 6 · `../infrastructure-and-deployment.md` |
| 5 | `05_local_dev.py` | `../img/05_local_dev.*` | NFR17 · `../infrastructure-and-deployment.md` |

## Conventions (so a diagram actually communicates)

- **Solid dark-blue edge = principal flow** · **dashed grey edge = backing dependency.**
- **Every edge carries a verb** (`ingested by`, `writes curated`, `routes-to-LLM`, `supplies-secrets`, `ships logs/traces`, …).
- **Clusters = layers / trust boundaries.** Light, high-contrast theme (`_theme.py`).
- Components with no built-in brand icon (Dagster, LangGraph/LangChain, MinIO) use the **closest semantic node with an authoritative label** — swap in a vendored PNG later for higher fidelity without changing the graph.

## Render

Prerequisites: Graphviz (`brew install graphviz` / `apt-get install -y graphviz`) — a **system** dependency, never pip.

```bash
cd docs/architecture/diagrams
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./render.sh          # writes PNG + SVG to ../img/ and inlines icons into the SVGs
```

Each script emits both **PNG** (embed in Markdown/READMEs) and **SVG** (crisp for docs sites). `embed_svg_images.py` base64-inlines the PNG node-icons into the SVGs so they are portable and leak no local paths (run automatically by `render.sh`).

## Files
- `_theme.py` — shared graph/node/edge styling + `principal()` / `backing()` / `cluster()` helpers.
- `0*.py` — one diagram each.
- `embed_svg_images.py` — SVG post-processor (idempotent).
- `render.sh` — render all + post-process.
- `requirements.txt` — `diagrams` pin.
