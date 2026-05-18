# DGX Spark Setup Guide

Getting Deep Thought 2.0 running on your DGX Spark from zero to first question.

---

## Prerequisites

- NVIDIA DGX Spark with DGX OS installed
- Internet connection (for initial model download only)
- SSH access or direct console

## Step 1: System Verification

```bash
# Verify GPU
nvidia-smi

# Expected output: GB110 GPU, 128GB unified memory
# If this fails, update NVIDIA drivers via DGX OS package manager

# Check CUDA
nvcc --version
# Expected: CUDA 12.x+

# Check available memory
free -h
```

## Step 2: Install Python Environment

```bash
# DGX OS ships with Python, but let's ensure we have 3.11+
python3 --version

# Create a virtual environment
python3 -m venv ~/deep-thought-env
source ~/deep-thought-env/bin/activate

# Install project dependencies
cd /path/to/eternalQuestion
pip install -e .

# Install vLLM (requires CUDA)
pip install vllm
```

## Step 3: Download Models

This is the longest step. Both models need to be downloaded from HuggingFace.

```bash
# Option A: Using huggingface-cli (recommended)
pip install huggingface-hub
huggingface-cli download google/gemma-4-26b-a4b-it
huggingface-cli download google/gemma-4-31b-it

# Option B: Using vLLM (downloads on first serve)
# Just start vLLM and it will download automatically

# Option C: Using Ollama (simpler but less control)
# curl -fsSL https://ollama.com/install.sh | sh
# ollama pull gemma4:26b
# ollama pull gemma4:31b
```

**Disk usage**: ~13GB (26B MoE FP8) + ~16GB (31B Dense FP8) = ~29GB total.

## Step 4: Start Model Servers

```bash
# From the project directory
bash scripts/start_vllm.sh

# This launches two vLLM instances:
# - Port 8001: Gemma 4 26B MoE (explorer)
# - Port 8002: Gemma 4 31B Dense (reasoner)

# Wait for both to report "READY"
# First startup downloads models if not cached (~10-30 min)
# Subsequent starts: ~30-60 seconds
```

### Verify model servers

```bash
# Check explorer
curl http://localhost:8001/v1/models | python3 -m json.tool

# Check reasoner
curl http://localhost:8002/v1/models | python3 -m json.tool

# Quick inference test
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-4-26b-a4b-it",
    "messages": [{"role": "user", "content": "What is 6 times 7?"}],
    "max_tokens": 50
  }'
```

## Step 5: Launch Deep Thought

```bash
# Full 24-hour run
bash scripts/run.sh 24

# Short test run (1 hour)
bash scripts/run.sh 1

# Quick smoke test (5 minutes)
bash scripts/run.sh 0.083
```

## Step 6: Monitor

### Terminal monitoring

```bash
# Watch live logs
tail -f logs/deep_thought_*.jsonl | python3 -m json.tool

# Watch leaderboard updates
watch -n 30 'python3 -c "
import sqlite3, json
conn = sqlite3.connect(\"logs/mcts_tree.db\")
rows = conn.execute(\"\"\"
    SELECT question, total_score/CASE WHEN visits>0 THEN visits ELSE 1 END as avg, visits
    FROM nodes WHERE visits > 0 AND parent_id IS NOT NULL
    ORDER BY avg DESC LIMIT 10
\"\"\").fetchall()
for i, (q, s, v) in enumerate(rows):
    print(f\"#{i+1} ({s:.2f}, {v} visits): {q[:80]}\")
"'
```

### GPU monitoring

```bash
# Real-time GPU stats
watch -n 2 nvidia-smi

# Or use nvitop (more detailed)
pip install nvitop
nvitop
```

## Step 7: Retrieve Results

```bash
# After the run completes (or anytime during):
cat logs/final_results.json | python3 -m json.tool

# Full report
cat logs/run_report.json | python3 -m json.tool

# Browse the full MCTS tree
sqlite3 logs/mcts_tree.db "
    SELECT id, question, visits,
           ROUND(total_score/CASE WHEN visits>0 THEN visits ELSE 1 END, 2) as avg
    FROM nodes
    WHERE visits > 0
    ORDER BY avg DESC
    LIMIT 20;
"
```

## Crash Recovery

The system is designed to survive crashes:

```bash
# If Deep Thought crashes, just restart:
bash scripts/run.sh 24

# It will:
# 1. Reconnect to the existing MCTS tree in SQLite
# 2. Continue from where it left off
# 3. No work is ever lost
```

## Alternative: Using Ollama Instead of vLLM

If you prefer Ollama's simplicity:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull models
ollama pull gemma4:26b
ollama pull gemma4:31b

# Update config/models.json:
# Change base_url to http://localhost:11434/v1
# Change model_id to gemma4:26b and gemma4:31b
```

Note: vLLM provides better throughput via continuous batching and PagedAttention,
but Ollama is simpler to set up.

## Alternative: Using Hermes Agent as Harness

For the full Hermes integration with self-improving skills:

```bash
# Install Hermes Agent
git clone https://github.com/NousResearch/hermes-agent
cd hermes-agent

# Configure to use local models
# Edit config to point at your vLLM instances

# Copy our skills into Hermes
cp /path/to/eternalQuestion/skills/*.py ~/.hermes/skills/

# Run Hermes with Deep Thought profile
hermes --profile deep-thought
```

See the Hermes Agent documentation for full setup instructions.

## Troubleshooting

| Issue | Solution |
|---|---|
| OOM during vLLM startup | Lower `gpu-memory-utilization` in config/models.json |
| Slow inference | Check that FP8 quantization is active in vLLM logs |
| Model download fails | Use `huggingface-cli download` with `--resume-download` |
| Port conflict | Change ports in config/models.json and scripts/start_vllm.sh |
| KV cache too small | Increase `gpu-memory-utilization` or decrease `max-model-len` |
| vLLM crashes mid-run | The watchdog in start_vllm.sh detects this; restart manually |

## Going Air-Gapped

After initial setup and model download:

1. All inference is local — no internet needed
2. SQLite tree is local
3. No telemetry or cloud dependencies
4. Disconnect from internet and run

The only thing that requires internet is the initial model download
and pip package installation.
