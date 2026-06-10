#!/bin/bash
# Run the public dashboard against the local experiment database.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR/web"

export DEEP_THOUGHT_DB_PATH="${DEEP_THOUGHT_DB_PATH:-$PROJECT_DIR/logs/deep_thought.db}"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-3000}"

if [ ! -d node_modules ]; then
    echo "[DASHBOARD] Installing npm dependencies..."
    npm install
fi

echo "[DASHBOARD] DB: $DEEP_THOUGHT_DB_PATH"
echo "[DASHBOARD] URL: http://$HOST:$PORT"
if [ -d .next ]; then
    npm run start -- --hostname "$HOST" --port "$PORT"
else
    npm run dev -- --hostname "$HOST" --port "$PORT"
fi
