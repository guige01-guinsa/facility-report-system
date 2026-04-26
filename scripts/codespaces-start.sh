#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_LOG="/tmp/facility-report-backend.log"
FRONTEND_LOG="/tmp/facility-report-frontend.log"

if ! command -v lsof >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y lsof
fi

if ! lsof -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  nohup bash "$ROOT/scripts/dev-backend.sh" >"$BACKEND_LOG" 2>&1 &
fi

if ! lsof -iTCP:3000 -sTCP:LISTEN >/dev/null 2>&1; then
  nohup bash "$ROOT/scripts/dev-frontend.sh" >"$FRONTEND_LOG" 2>&1 &
fi

echo "Backend log: $BACKEND_LOG"
echo "Frontend log: $FRONTEND_LOG"
