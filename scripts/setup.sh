#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

if [ ! -f "$BACKEND/.env" ]; then
  cp "$BACKEND/.env.example" "$BACKEND/.env"
fi

if [ ! -f "$FRONTEND/.env.local" ]; then
  cp "$FRONTEND/.env.example" "$FRONTEND/.env.local"
fi

if [ ! -x "$BACKEND/.venv/bin/python" ]; then
  python3 -m venv "$BACKEND/.venv"
fi

"$BACKEND/.venv/bin/python" -m pip install -r "$BACKEND/requirements.txt"

cd "$FRONTEND"
npm install
