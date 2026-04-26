#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

if [ ! -x "$BACKEND/.venv/bin/python" ]; then
  echo "Backend virtual environment is missing. Run scripts/setup.sh first." >&2
  exit 1
fi

cd "$BACKEND"
".venv/bin/python" -m compileall app
".venv/bin/python" -m unittest discover -s tests -p "test_*.py" -v

cd "$FRONTEND"
npm run build
