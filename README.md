# Deep Thought 2.0

**Finding the Ultimate Question of Life, the Universe, and Everything.**

*Deep Thought took 7.5 million years. We're giving it 24 hours and a GPU.*

---

In Douglas Adams' Hitchhiker's Guide to the Galaxy, the supercomputer Deep
Thought computed for 7.5 million years and returned **42** as the Answer to the
Ultimate Question of Life, the Universe, and Everything. But nobody knew what
the Question was.

This project rebuilds Deep Thought on a desk. A 24-hour autonomous AI
experiment running on NVIDIA DGX Spark, using Monte Carlo Tree Search +
Adversarial Debate to find the Question whose answer is 42.

## Architecture

```
MCTS Tree Search (generates candidate questions)
        │
        ▼
Adversarial Debate (two AIs argue for/against each candidate)
        │
        ▼
Judge Evaluation (scores on 4 axes: math, philosophy, humor, universality)
        │
        ▼
Backpropagation (updates tree, best candidates rise to the top)
        │
        ▼
AutoResearch Loop (meta-optimizes the system's own parameters)
```

**Two local models running simultaneously:**
- **Gemma 4 26B MoE** (4B active params) — fast question generation
- **Gemma 4 31B Dense** — deep reasoning for debates and judging

Everything runs locally. No cloud. No API calls. Just a GPU contemplating
existence.

## Quick Start

```bash
# 1. Install
pip install -e .

# 2. Start model servers (requires GPU + vLLM)
bash scripts/start_vllm.sh

# 3. Run Deep Thought (default: 24 hours)
bash scripts/run.sh

# Short test run:
bash scripts/run.sh 1
```

## How It Works

### MCTS + Debate

1. **Select**: UCB1 picks the most promising unexplored branch
2. **Expand**: The 26B MoE generates 3-5 candidate questions (fast, creative)
3. **Debate**: Two 31B Dense agents argue FOR and AGAINST each candidate
4. **Judge**: A third 31B agent scores the debate on 4 axes (0-10 each)
5. **Backpropagate**: Scores flow up the tree; good questions rise

### Scoring Rubric

| Axis | Weight | What It Measures |
|---|---|---|
| Mathematical | 0.25 | Does the answer naturally equal 42? |
| Philosophical | 0.30 | Does it address life, the universe, everything? |
| Humor | 0.25 | Would Douglas Adams approve? |
| Universality | 0.20 | Would all conscious beings ask this? |

### AutoResearch (Karpathy Pattern)

A meta-optimization loop modifies the system's own parameters during the run.
The LLM proposes parameter changes, runs experiments, keeps improvements, rolls
back failures. The system literally improves its own brain over 24 hours.

### Phases

| Phase | Hours | Strategy |
|---|---|---|
| Warm-up | 0-1 | Seed tree, calibrate scoring |
| Exploration | 1-8 | High exploration, broad search, quick debates |
| Exploitation | 8-16 | Deep debates on top candidates |
| Convergence | 16-23 | Refine and cross-pollinate best candidates |
| Final Judgment | 23-24 | Tournament bracket of top 8 |

## Requirements

- **Hardware**: NVIDIA DGX Spark (128GB unified memory) or equivalent GPU setup
- **Software**: Python 3.11+, vLLM, CUDA 12+
- **Models**: Gemma 4 26B MoE + Gemma 4 31B Dense (downloaded automatically)

## Project Structure

```
eternalQuestion/
├── src/
│   ├── orchestrator.py    # Main 24-hour loop
│   ├── mcts.py            # Monte Carlo Tree Search engine
│   ├── debate.py          # Adversarial debate arena
│   ├── expander.py        # Question generation
│   ├── autoresearch.py    # Karpathy-style meta-optimization
│   ├── llm_client.py      # vLLM API client
│   └── logger_setup.py    # Structured logging
├── config/
│   └── models.json        # Model serving configuration
├── scripts/
│   ├── start_vllm.sh      # Launch model servers
│   ├── run.sh             # Launch Deep Thought
│   └── stop.sh            # Graceful shutdown
├── docs/
│   ├── SETUP.md           # DGX Spark setup guide
│   └── MARKETING.md       # Marketing playbook
├── logs/                  # Runtime artifacts
│   ├── mcts_tree.db       # SQLite: full MCTS tree (crash-recoverable)
│   ├── debates/           # Full debate transcripts
│   └── final_results.json # Top candidates with scores
└── PLAN.md                # Full architecture document
```

## Crash Recovery

The MCTS tree is persisted in SQLite. If Deep Thought crashes at hour 18, just
restart — it resumes from the last state. No work is ever lost.

```bash
# Crashed? Just restart.
bash scripts/run.sh
```

## Monitoring

```bash
# Live leaderboard
watch -n 30 'sqlite3 logs/mcts_tree.db "
  SELECT question, ROUND(total_score/visits, 2) as avg, visits
  FROM nodes WHERE visits > 0 AND parent_id IS NOT NULL
  ORDER BY avg DESC LIMIT 10"'

# GPU stats
watch -n 2 nvidia-smi
```

## License

MIT

## Acknowledgments

- Douglas Adams, for the question (and the answer)
- NVIDIA, for putting a petaflop on a desk
- Andrej Karpathy, for the autoresearch pattern
- Nous Research, for Hermes Agent
- Google, for Gemma 4

*The answer is 42. Now let's find the Question.*
