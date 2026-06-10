#!/bin/bash
# Stop all Deep Thought 2.0 processes

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"

echo "[STOP] Stopping Deep Thought 2.0..."

# Kill vLLM servers
if [ -f "$LOG_DIR/explorer.pid" ]; then
    kill "$(cat "$LOG_DIR/explorer.pid")" 2>/dev/null && echo "[STOP] Explorer stopped" || echo "[STOP] Explorer already stopped"
    rm -f "$LOG_DIR/explorer.pid"
fi

if [ -f "$LOG_DIR/reasoner.pid" ]; then
    kill "$(cat "$LOG_DIR/reasoner.pid")" 2>/dev/null && echo "[STOP] Reasoner stopped" || echo "[STOP] Reasoner already stopped"
    rm -f "$LOG_DIR/reasoner.pid"
fi

# Kill any remaining vllm processes
pkill -f "vllm serve" 2>/dev/null && echo "[STOP] Killed remaining vLLM processes" || true

echo "[STOP] All processes stopped."
echo "[STOP] Your experiment database is safe in: logs/deep_thought.db"
echo "[STOP] Resume anytime by running: bash scripts/run.sh"
