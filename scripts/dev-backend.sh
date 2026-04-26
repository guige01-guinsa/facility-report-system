#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

if [ ! -f ".env" ]; then
  cp ".env.example" ".env"
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Backend virtual environment is missing. Run scripts/setup.sh first." >&2
  exit 1
fi

".venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
