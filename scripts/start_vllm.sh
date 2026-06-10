#!/bin/bash
# ============================================================
# Deep Thought 2.0 — vLLM Model Server Launcher
# Starts two vLLM instances: Explorer (E4B) + Reasoner (26B MoE)
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
export PATH="$PROJECT_DIR/.venv/bin:$PATH"
VLLM_BIN="$PROJECT_DIR/.venv/bin/vllm"
if [ ! -x "$VLLM_BIN" ]; then
    VLLM_BIN="$(command -v vllm || true)"
fi
EXPLORER_PID=""
REASONER_PID=""

cleanup_models() {
    if [ -n "${EXPLORER_PID:-}" ]; then
        kill "$EXPLORER_PID" 2>/dev/null || true
    fi
    if [ -n "${REASONER_PID:-}" ]; then
        kill "$REASONER_PID" 2>/dev/null || true
    fi
}

trap cleanup_models EXIT INT TERM

echo "============================================"
echo "  Deep Thought 2.0 — Model Server Startup"
echo "============================================"
echo ""

# --- Check prerequisites ---
if [ -z "$VLLM_BIN" ] || [ ! -x "$VLLM_BIN" ]; then
    echo "[ERROR] vLLM not found. Install with: uv venv .venv --python python3 && source .venv/bin/activate && uv pip install -e '.[serve]'"
    exit 1
fi

if ! nvidia-smi &>/dev/null; then
    echo "[ERROR] nvidia-smi not found. Check GPU drivers."
    exit 1
fi

echo "[SYSTEM] GPU status:"
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader
echo ""

# --- Launch Explorer (Gemma 4 E4B) ---
echo "[LAUNCH] Starting Explorer model (Gemma 4 E4B) on port 8001..."
"$VLLM_BIN" serve google/gemma-4-E4B-it \
    --port 8001 \
    --dtype auto \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.13 \
    --max-num-seqs 1 \
    --quantization fp8 \
    --kv-cache-dtype fp8 \
    --trust-remote-code \
    > "$LOG_DIR/vllm_explorer.log" 2>&1 &

EXPLORER_PID=$!
echo "[LAUNCH] Explorer PID: $EXPLORER_PID"

# Wait for explorer to load
echo "[WAIT] Waiting for Explorer to load model..."
for i in $(seq 1 1800); do
    if curl -s http://localhost:8001/health >/dev/null 2>&1; then
        echo "[READY] Explorer is ready on port 8001"
        break
    fi
    if [ $i -eq 1800 ]; then
        echo "[ERROR] Explorer failed to start within 1800s"
        kill $EXPLORER_PID 2>/dev/null || true
        exit 1
    fi
    sleep 1
done

MEM_AVAILABLE_GIB="$(awk '/MemAvailable/ { printf "%.0f", $2 / 1024 / 1024 }' /proc/meminfo)"
MIN_REASONER_START_GIB="${MIN_REASONER_START_GIB:-75}"
echo "[SYSTEM] Memory available after Explorer load: ${MEM_AVAILABLE_GIB} GiB"
if [ "$MEM_AVAILABLE_GIB" -lt "$MIN_REASONER_START_GIB" ]; then
    echo "[ERROR] Refusing to start Reasoner: need at least ${MIN_REASONER_START_GIB} GiB available, found ${MEM_AVAILABLE_GIB} GiB."
    echo "[ERROR] Use sequential serving or a pre-quantized smaller-footprint checkpoint."
    exit 1
fi

# --- Launch Reasoner (Gemma 4 26B MoE) ---
echo "[LAUNCH] Starting Reasoner model (Gemma 4 26B MoE) on port 8002..."
"$VLLM_BIN" serve google/gemma-4-26b-a4b-it \
    --port 8002 \
    --dtype auto \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.55 \
    --max-num-seqs 1 \
    --enable-prefix-caching \
    --quantization fp8 \
    --kv-cache-dtype fp8 \
    --trust-remote-code \
    > "$LOG_DIR/vllm_reasoner.log" 2>&1 &

REASONER_PID=$!
echo "[LAUNCH] Reasoner PID: $REASONER_PID"

# Wait for reasoner to load
echo "[WAIT] Waiting for Reasoner to load model..."
for i in $(seq 1 1800); do
    if curl -s http://localhost:8002/health >/dev/null 2>&1; then
        echo "[READY] Reasoner is ready on port 8002"
        break
    fi
    if [ $i -eq 1800 ]; then
        echo "[ERROR] Reasoner failed to start within 1800s"
        kill $EXPLORER_PID $REASONER_PID 2>/dev/null || true
        exit 1
    fi
    sleep 1
done

echo ""
echo "============================================"
echo "  Both models are loaded and serving"
echo "  Explorer (E4B): http://localhost:8001"
echo "  Reasoner (26B MoE): http://localhost:8002"
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
cleanup_models
