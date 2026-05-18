# The Eternal Question: Finding What 42 Answers

## Project Deep Thought 2.0

A 24-hour autonomous AI experiment running on NVIDIA DGX Spark to find the
Ultimate Question of Life, the Universe, and Everything — the one whose answer
is 42.

---

## The Problem

In Douglas Adams' *Hitchhiker's Guide to the Galaxy*, the supercomputer Deep
Thought computed for 7.5 million years and returned **42** as the Answer to the
Ultimate Question of Life, the Universe, and Everything. But nobody knew what
the Question was. The Earth was built to find it, ran for 10 million years, and
was destroyed 5 minutes before completing.

Arthur Dent's corrupted subconscious produced: *"What do you get if you multiply
six by nine?"* — which equals 54, not 42. The data was corrupted by
Golgafrinchans contaminating the Earth's computational matrix.

**We are rebuilding Deep Thought. On a desk. In 24 hours.**

---

## Architecture: Hybrid MCTS + Debate

### Why This Architecture

| Component | Purpose | Model |
|---|---|---|
| **MCTS Explorer** | Generate and expand candidate questions via tree search | Gemma 4 26B MoE (fast: 4B active params) |
| **Debate Arena** | Adversarial evaluation of candidate questions | Gemma 4 31B Dense (deep reasoning) |
| **Judge** | Score debates, update MCTS tree values | Gemma 4 31B Dense |
| **Skill Learner** | Hermes self-improving loop refines search strategies | Hermes Agent core |

### Flow

```
                    ┌─────────────────────────┐
                    │     MCTS Root Node       │
                    │  "The Ultimate Question"  │
                    └───────────┬─────────────┘
                                │
                    ┌───────────┴──────────────┐
                    │      SELECT (UCB1)        │
                    │  Pick most promising node  │
                    └───────────┬──────────────┘
                                │
                    ┌───────────┴──────────────┐
                    │      EXPAND               │
                    │  Gemma 4 26B MoE generates │
                    │  child candidate questions │
                    └───────────┬──────────────┘
                                │
                    ┌───────────┴──────────────┐
                    │      SIMULATE (Debate)    │
                    │  Two Gemma 4 31B agents   │
                    │  argue FOR and AGAINST    │
                    │  each candidate question  │
                    └───────────┬──────────────┘
                                │
                    ┌───────────┴──────────────┐
                    │      EVALUATE (Judge)     │
                    │  31B scores debate on:    │
                    │  - Mathematical fit (=42) │
                    │  - Philosophical depth    │
                    │  - Humor / Adams-ness     │
                    │  - Universality           │
                    └───────────┬──────────────┘
                                │
                    ┌───────────┴──────────────┐
                    │      BACKPROPAGATE        │
                    │  Update tree node values   │
                    │  Propagate scores upward   │
                    └──────────────────────────┘
                                │
                          (repeat 24hrs)
```

### MCTS Details

- **Selection**: UCB1 formula with exploration constant C=1.414
- **Expansion**: Generate 3-5 child questions per node
- **Simulation**: Full debate round (3 exchanges each side)
- **Backpropagation**: Weighted average of judge scores
- **Tree persistence**: SQLite database, survives crashes

### Debate Protocol

Each candidate question is debated:

1. **Proposer** (31B): Argues why this IS the Ultimate Question
2. **Opponent** (31B): Argues why it is NOT
3. Three rounds of rebuttal each
4. **Judge** (31B): Scores on 4 axes (0-10 each):
   - **Mathematical**: Does the question's answer equal 42?
   - **Philosophical**: Does it address life, the universe, everything?
   - **Humor**: Would Douglas Adams approve?
   - **Universality**: Is it a question worth asking?

---

## Model Strategy: Why Gemma 4 Dual-Model

### Gemma 4 26B MoE — The Explorer

| Attribute | Value |
|---|---|
| Architecture | Mixture of Experts, 128 experts, top-8 routing |
| Total params | 26B (must all be in memory) |
| Active params | 4B per token |
| Context | 256K tokens |
| Role | MCTS expansion — generate candidate questions FAST |

**Why MoE for exploration**: MCTS needs volume. The explorer generates hundreds
of candidate questions. With only 4B active parameters per forward pass, the
26B MoE achieves ~3-5x the throughput of the 31B dense model. More rollouts =
better tree coverage = higher chance of finding the real Question.

### Gemma 4 31B Dense — The Debater/Judge

| Attribute | Value |
|---|---|
| Architecture | Dense transformer |
| Total params | 31B |
| Active params | 31B (all active, all the time) |
| Context | 256K tokens |
| Role | Debate + Judging — deep reasoning on candidates |

**Why dense for evaluation**: Debate requires sustained coherent reasoning
across long arguments. Dense models maintain more consistent quality than MoE
for multi-turn logical argumentation. The judge needs to weigh subtle
philosophical and mathematical nuances — this demands full parameter
utilization.

### Memory Budget on DGX Spark (128GB Unified)

```
Component                          Memory (FP8)
─────────────────────────────────────────────────
Gemma 4 31B Dense weights          ~16 GB
Gemma 4 26B MoE weights            ~13 GB
vLLM engine overhead (x2)          ~4 GB
KV Cache (31B, 16K ctx, Q4)        ~2 GB
KV Cache (26B, 16K ctx, Q4)        ~1.5 GB
SQLite + Python + Hermes           ~2 GB
Monitoring (Prometheus/Grafana)    ~1 GB
─────────────────────────────────────────────────
TOTAL                              ~39.5 GB
REMAINING HEADROOM                 ~88.5 GB
```

The 88.5 GB headroom means we can:
- Increase context windows significantly
- Run more concurrent requests through vLLM batching
- Never worry about OOM in a 24-hour run

### KV Cache Strategy

The full 256K context window requires 218GB for the 31B model without
quantization — obviously impossible on 128GB. Our strategy:

1. **Cap context at 16K-32K tokens** via `--max-model-len` in vLLM
2. **Use KV cache Q4 quantization** in vLLM (0.038 MB/token)
3. **vLLM PagedAttention** for efficient memory allocation
4. **Sliding window attention** for the MoE model's local layers
5. **Periodic context pruning**: Summarize old debate history, keep only
   relevant nodes in context

This gives us fast inference with controlled memory — exactly what a 24-hour
run needs.

---

## Agent Harness: Hermes Agent

### Why Hermes Over OpenClaw/LangGraph

| Feature | Hermes | OpenClaw | LangGraph |
|---|---|---|---|
| DGX Spark | NVIDIA official feature | NemoClaw stack | DIY |
| Self-improving | Skill learning loop | No | No |
| Sub-agents | Isolated sub-agents | No multi-agent | Graph nodes |
| Always-on design | Yes, core feature | Chat-focused | Loop required |
| GitHub stars | 140K+ | Growing fast | ~10K |
| Memory/persistence | Built-in layered memory | Session persistence | SQLite checkpointer |

### Hermes Integration

```
Hermes Agent (orchestrator)
├── Skill: mcts_search
│   ├── Manages MCTS tree in SQLite
│   ├── Calls vLLM (26B MoE) for expansion
│   └── Triggers debates for promising nodes
├── Skill: debate_round
│   ├── Calls vLLM (31B Dense) for proposer
│   ├── Calls vLLM (31B Dense) for opponent
│   └── Calls vLLM (31B Dense) for judge
├── Skill: evaluate_and_rank
│   ├── Reads top candidates from tree
│   └── Produces ranked leaderboard
├── Skill: self_improve
│   ├── Hermes analyzes which question categories score highest
│   ├── Refines expansion prompts based on learnings
│   └── Adjusts exploration vs exploitation balance
└── Memory: persistent session memory across all 24 hours
```

### Hermes Profiles

We run two Hermes profiles on the same DGX Spark:

1. **deep-thought**: The main MCTS+Debate orchestrator
2. **marvin**: A monitoring/reporting agent that:
   - Logs progress every 30 minutes
   - Generates intermediate leaderboards
   - Detects stalled branches and alerts

---

## Evaluation Criteria

The judge scores each candidate question on these axes:

### 1. Mathematical Fitness (0-10)
Does the question naturally produce 42 as its answer?
- "How many roads must a man walk down?" → 42 (per the book)
- "What is 6 times 7?" → 42 (obvious, low philosophical score)
- "What is 6 times 9?" → 54 (corrupted data, score 0)

### 2. Philosophical Depth (0-10)
Does it genuinely address the meaning of life, the universe, everything?
- A question about grocery shopping → 0
- A question about consciousness, existence, purpose → 8-10

### 3. Adams Humor Score (0-10)
Would Douglas Adams find this funny? Is it absurd in the right way?
- Too serious → low score
- Too silly → low score
- Perfectly absurd (the answer is both meaningful AND meaningless) → 10

### 4. Universality (0-10)
Is this a question that all conscious beings would eventually ask?
- Human-specific questions → low score
- Questions about existence itself → high score

### Composite Score
`score = 0.25 * math + 0.30 * philosophy + 0.25 * humor + 0.20 * universality`

Philosophy weighted highest because Adams' own commentary suggests the joke is
about the futility of seeking simple answers to deep questions.

---

## 24-Hour Run Strategy

### Hour 0-1: Warm-up Phase
- Boot vLLM with both models
- Seed MCTS tree with 10 known candidate questions from lore
- Run initial debate rounds to calibrate scoring
- Hermes creates initial skills

### Hour 1-8: Exploration Phase
- High exploration constant (C=2.0)
- Generate breadth: aim for 500+ unique candidate questions
- Quick shallow debates (1 round each)
- Hermes learns which question categories are promising

### Hour 8-16: Exploitation Phase
- Lower exploration constant (C=1.0)
- Deep debates (3 rounds) on top 50 candidates
- Prune branches scoring below 4.0/10 composite
- Hermes refines expansion prompts based on high-scoring patterns

### Hour 16-23: Convergence Phase
- Very low exploration (C=0.5)
- Full 3-round debates on top 20 candidates
- Cross-pollination: combine elements of high-scoring questions
- Generate "mutation" variants of top candidates

### Hour 23-24: Final Judgment
- Tournament bracket: top 8 candidates debate head-to-head
- Final ranking produced
- Generate report with full reasoning chain

### Crash Recovery
- MCTS tree in SQLite: survives any crash
- Hermes session persistence: resume from last state
- vLLM auto-restart via systemd watchdog
- Every node scored is permanent — no work is ever lost

---

## Logging & Observability

### Log Levels
```
[MCTS]     Tree operations: expand, select, backpropagate
[DEBATE]   Full debate transcripts with timestamps
[JUDGE]    Scoring breakdowns per axis
[HERMES]   Skill creation/refinement events
[SYSTEM]   GPU utilization, memory, tokens/sec
[LEADER]   Leaderboard updates every 30 minutes
```

### Live Dashboard
- Prometheus metrics from vLLM (tokens/sec, queue depth, memory)
- Grafana dashboard with:
  - MCTS tree depth over time
  - Top candidates leaderboard (live)
  - GPU utilization and temperature
  - Debate count / hour
  - Score distribution histogram

### Artifacts
```
logs/
├── mcts_tree.db          # SQLite: full tree with all scores
├── debates/              # Full debate transcripts (JSON)
├── leaderboard.json      # Current top 50 with scores
├── hermes_skills/        # Skills Hermes learned
├── metrics/              # Prometheus snapshots
└── final_report.md       # Generated at hour 24
```

---

## AutoResearch Loop (Karpathy Pattern)

Inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch)
(66K+ GitHub stars), we add a meta-optimization layer that modifies the system's
own parameters during the 24-hour run.

### How It Works

```
┌──────────────────────────────────┐
│     AutoResearch Meta-Loop       │
│                                  │
│  1. Read current config          │
│  2. LLM proposes a hypothesis    │
│     (change ONE parameter)       │
│  3. Run 10-minute experiment     │
│     window with new config       │
│  4. Measure: top-10 avg score    │
│  5. If improved → KEEP change    │
│     If not → ROLLBACK            │
│  6. Log everything               │
│  7. Repeat                       │
└──────────────────────────────────┘
```

### What Gets Optimized

| Parameter | Description | Default |
|---|---|---|
| `math_weight` | Scoring rubric: mathematical fitness | 0.25 |
| `philosophy_weight` | Scoring rubric: philosophical depth | 0.30 |
| `humor_weight` | Scoring rubric: Adams humor | 0.25 |
| `universality_weight` | Scoring rubric: universal appeal | 0.20 |
| `exploration_constant` | MCTS UCB1 C parameter | 1.414 |
| `expand_count` | Questions generated per expansion | 5 |
| `debate_rounds` | Rounds per debate | 3 |
| `expansion_temperature` | Creativity of question generation | 0.9 |
| `proposer_temperature` | Debate argument creativity | 0.7 |

### Why This Matters

Karpathy's insight: let the AI optimize its own research process. In his
original autoresearch, the loop improved nanochat training from 2.02 hours to
1.80 hours over 700 experiments.

In our case, the system learns:
- Which scoring weights produce the most interesting questions
- How creative to be when generating candidates (temperature)
- How deep to debate (rounds) — diminishing returns?
- Whether to explore broadly or exploit deeply (C parameter)

The autoresearch loop runs on top of the MCTS+Debate loop, meta-optimizing
the search process itself. It is Deep Thought improving its own brain.

---

## Tech Stack Summary

| Layer | Technology |
|---|---|
| Hardware | NVIDIA DGX Spark (128GB, Grace Blackwell) |
| OS | DGX OS (Ubuntu-based) |
| Model Serving | vLLM (two instances, OpenAI-compatible API) |
| Models | Gemma 4 31B Dense (FP8) + Gemma 4 26B MoE (FP8) |
| Agent Harness | Hermes Agent (NousResearch) |
| MCTS Engine | Custom Python (src/mcts.py) |
| Debate Engine | Custom Python (src/debate.py) |
| Persistence | SQLite (tree) + Hermes memory (session) |
| Monitoring | Prometheus + Grafana |
| Logging | Structured JSON logs + rich console output |
| Language | Python 3.11+ |

---

## What We Expect to Find

Honestly? We do not know. That is the point.

Adams said there is no real question — that the joke IS the absence of a
satisfying answer. But maybe that is because Deep Thought did not have Mixture
of Experts routing, adversarial debate, and Monte Carlo Tree Search.

If the agents converge on something, it will be one of:

1. **A mathematically valid question** where 42 is the natural answer
2. **A philosophically resonant question** that captures the absurdity Adams intended
3. **Something we did not expect** — which would be the most Adams-like outcome

The real product is the journey: 24 hours of autonomous AI reasoning about the
meaning of existence, logged and observable, running on hardware you can put on
your desk.

Deep Thought took 7.5 million years. We are giving it 24 hours and a GPU.
Let's see what happens.
