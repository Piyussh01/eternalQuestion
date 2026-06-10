#!/bin/bash
# ============================================================
# Deep Thought 2.0 — Main Launch Script
# Runs the full 24-hour experiment
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

HOURS="${1:-24}"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

echo "============================================"
echo "  DEEP THOUGHT 2.0"
echo "  Meaning of Life"
echo "  Runtime: ${HOURS} hours"
echo "  Started: $(date)"
echo "============================================"
echo ""

# Check if vLLM servers are running
echo "[CHECK] Verifying model servers..."
if ! curl -s http://localhost:8001/health >/dev/null 2>&1; then
    echo "[ERROR] Explorer model server not running on port 8001"
    echo "[ERROR] Run: bash scripts/start_vllm.sh"
    exit 1
fi

if ! curl -s http://localhost:8002/health >/dev/null 2>&1; then
    echo "[ERROR] Reasoner model server not running on port 8002"
    echo "[ERROR] Run: bash scripts/start_vllm.sh"
    exit 1
fi

echo "[CHECK] Both model servers are healthy"
echo ""

# Create logs directory
mkdir -p logs/debates

# Launch the orchestrator
echo "[LAUNCH] Starting Deep Thought orchestrator..."
"$PYTHON_BIN" -m src.orchestrator --hours "$HOURS"

echo ""
echo "[DONE] Deep Thought 2.0 has finished."
echo "[DONE] Results: logs/final_results.json"
echo "[DONE] Full report: logs/run_report.json"
echo "[DONE] Experiment database: logs/deep_thought.db"
