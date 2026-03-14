#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$ROOT/.runtime"
mkdir -p "$RUNTIME_DIR"

if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3)"
fi

exec "$PYTHON_BIN" "$ROOT/service.py"
