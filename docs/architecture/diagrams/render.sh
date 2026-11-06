#!/usr/bin/env bash
# Render all IKIP architecture diagrams to ../img/*.{png,svg}
# Requires: Graphviz `dot` on PATH, and a venv with `diagrams` installed.
#   python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${DIR}/venv/bin/python"
[ -x "$PY" ] || PY="python3"

mkdir -p "${DIR}/../img"
cd "$DIR"

for f in 01_system_context 02_ingestion_pipeline 03_rag_workflow 04_azure_deployment 05_local_dev; do
  echo ">> ${f}.py"
  "$PY" "${f}.py"
done

echo ">> embedding PNG icons into SVGs"
"$PY" embed_svg_images.py

echo "Done. Output in ${DIR}/../img/"
