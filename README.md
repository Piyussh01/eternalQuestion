# Deep Thought 2.0

**A 24-hour local AI experiment to answer one question: what is the meaning of life?**

This project runs two local models on NVIDIA DGX Spark. A small model generates
perspective questions; a larger model turns those perspectives into candidate
answers, critiques them, and keeps narrowing toward one answer. The goal is the
answer to the meaning of life, nothing more and nothing less.

The experiment runs locally: vLLM model servers, the Python orchestrator, and
SQLite history stay on the Spark. For a public website, a read-only exporter can
mirror public trace rows to Supabase while Vercel serves the Next.js dashboard.

## Architecture

```
Gemma 4 E4B generates perspective questions
birth, death, love, suffering, science, faith, ecology, art
        │
        ▼
Gemma 4 26B MoE synthesizes candidate answers
        │
        ▼
Model comparison
26B defends, E4B stress-tests, 26B judges
        │
        ▼
SQLite leaderboard + elimination history
        │
        ▼
Supabase public mirror + Vercel dashboard
        │
        ▼
AutoResearch proposes conservative process changes
```

## Models

- **Explorer / Perspective Generator**: `google/gemma-4-E4B-it` on port `8001`
  - High-temperature generation of lenses, probes, and perspective questions.
- **Reasoner / MoE**: `google/gemma-4-26b-a4b-it` on port `8002`
  - Lower-temperature answer synthesis, critique, and judging.

Serving is tuned for DGX Spark: both models use FP8 and FP8 KV cache. The E4B
server uses 4k context, one sequence, and a small KV allocation because it only
writes perspective prompts. The 26B MoE server keeps 8k context and a
conservative one-sequence setting because it does the answer synthesis,
critique, and judging.

The dashboard and logs show public model outputs: candidate answers, advocacy,
critique, judge reasoning, scores, and ranking changes. They do not expose or
claim hidden chain-of-thought.

## Scoring

Each answer is scored from 0-10 on four axes:


| Axis         | Weight | Meaning                                                    |
| ------------ | ------ | ---------------------------------------------------------- |
| Directness   | 0.30   | Answers the meaning of life, nothing more and nothing less |
| Depth        | 0.30   | Carries real philosophical weight without padding          |
| Universality | 0.20   | Applies across many kinds of conscious beings              |
| Resilience   | 0.20   | Survives critique from the opposing model                  |


## 24-Hour Phases


| Phase          | Hours | Strategy                                            |
| -------------- | ----- | --------------------------------------------------- |
| Warm-up        | 0-1   | Seed answers and calibrate perspective probes       |
| Exploration    | 1-12  | Sweep many perspectives across human experience     |
| Refinement     | 12-20 | Attack stronger answers from neglected perspectives |
| Consensus      | 20-23 | Compress recurring truths into shorter candidates   |
| Final Judgment | 23-24 | Re-evaluate top answers with full comparisons       |


## Quick Start

```bash
pip install -e ".[dev,serve]"
bash scripts/start_vllm.sh
bash scripts/run.sh          # default: 24 hours
bash scripts/run.sh 1        # one-hour test run
```

`scripts/start_vllm.sh` calls `vllm serve` for both Hugging Face model IDs.
On first run, vLLM downloads model weights into the Hugging Face cache. If
Hugging Face requires access approval for a model, run `huggingface-cli login`
on the Spark or set `HF_TOKEN` before starting the servers.

Outputs are written to:

- `logs/deep_thought.db` - SQLite candidate/evaluation history
- `logs/run_report.json` - full run summary

## AutoResearch

AutoResearch is intentionally conservative. It can adjust process parameters
such as perspectives per cycle, answers per perspective, comparison rounds,
generation temperature, and generation prompt suffixes. It promotes changes only
after repeated wins above a margin, reducing overfitting to noisy self-scores.

## License

MIT