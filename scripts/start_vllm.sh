#!/bin/bash
# ============================================================
# Deep Thought 2.0 — vLLM Model Server Launcher
# Starts two vLLM instances: Explorer (26B MoE) + Reasoner (31B Dense)
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

echo "============================================"
echo "  Deep Thought 2.0 — Model Server Startup"
echo "============================================"
echo ""

# --- Check prerequisites ---
if ! command -v vllm &>/dev/null; then
    echo "[ERROR] vLLM not found. Install with: pip install vllm"
    exit 1
fi

if ! nvidia-smi &>/dev/null; then
    echo "[ERROR] nvidia-smi not found. Check GPU drivers."
    exit 1
fi

echo "[SYSTEM] GPU status:"
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader
echo ""

# --- Launch Explorer (Gemma 4 26B MoE) ---
echo "[LAUNCH] Starting Explorer model (Gemma 4 26B MoE) on port 8001..."
vllm serve google/gemma-4-26b-a4b-it \
    --port 8001 \
    --dtype auto \
    --max-model-len 16384 \
    --gpu-memory-utilization 0.40 \
    --max-num-seqs 8 \
    --enable-prefix-caching \
    --quantization fp8 \
    --trust-remote-code \
    --disable-log-requests \
    2>&1 | tee "$LOG_DIR/vllm_explorer.log" &

EXPLORER_PID=$!
echo "[LAUNCH] Explorer PID: $EXPLORER_PID"

# Wait for explorer to load
echo "[WAIT] Waiting for Explorer to load model..."
for i in $(seq 1 120); do
    if curl -s http://localhost:8001/health >/dev/null 2>&1; then
        echo "[READY] Explorer is ready on port 8001"
        break
    fi
    if [ $i -eq 120 ]; then
        echo "[ERROR] Explorer failed to start within 120s"
        kill $EXPLORER_PID 2>/dev/null || true
        exit 1
    fi
    sleep 1
done

# --- Launch Reasoner (Gemma 4 31B Dense) ---
echo "[LAUNCH] Starting Reasoner model (Gemma 4 31B Dense) on port 8002..."
vllm serve google/gemma-4-31b-it \
    --port 8002 \
    --dtype auto \
    --max-model-len 32768 \
    --gpu-memory-utilization 0.55 \
    --max-num-seqs 4 \
    --enable-prefix-caching \
    --quantization fp8 \
    --trust-remote-code \
    --disable-log-requests \
    2>&1 | tee "$LOG_DIR/vllm_reasoner.log" &

REASONER_PID=$!
echo "[LAUNCH] Reasoner PID: $REASONER_PID"

# Wait for reasoner to load
echo "[WAIT] Waiting for Reasoner to load model..."
for i in $(seq 1 180); do
    if curl -s http://localhost:8002/health >/dev/null 2>&1; then
        echo "[READY] Reasoner is ready on port 8002"
        break
    fi
    if [ $i -eq 180 ]; then
        echo "[ERROR] Reasoner failed to start within 180s"
        kill $EXPLORER_PID $REASONER_PID 2>/dev/null || true
        exit 1
    fi
    sleep 1
done

echo ""
echo "============================================"
echo "  Both models are loaded and serving"
echo "  Explorer (26B MoE): http://localhost:8001"
echo "  Reasoner (31B Dense): http://localhost:8002"
echo "============================================"
echo ""
echo "PIDs: Explorer=$EXPLORER_PID Reasoner=$REASONER_PID"
echo "Logs: $LOG_DIR/vllm_explorer.log, $LOG_DIR/vllm_reasoner.log"
echo ""
echo "To stop: kill $EXPLORER_PID $REASONER_PID"

# Save PIDs for cleanup
echo "$EXPLORER_PID" > "$LOG_DIR/explorer.pid"
echo "$REASONER_PID" > "$LOG_DIR/reasoner.pid"

# Wait for either process to exit
wait -n $EXPLORER_PID $REASONER_PID
echo "[WARN] A vLLM process exited. Stopping remaining..."
kill $EXPLORER_PID $REASONER_PID 2>/dev/null || true
