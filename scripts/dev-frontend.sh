#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/frontend"

if [ ! -f ".env.local" ]; then
  cp ".env.example" ".env.local"
fi

if [ ! -d "node_modules" ]; then
  npm install
fi

npm run dev -- --port "${PORT:-3000}"
