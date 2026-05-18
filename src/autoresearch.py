"""
AutoResearch Loop for Deep Thought 2.0

Inspired by Karpathy's autoresearch: an autonomous experimentation loop
that modifies the system's own parameters, runs experiments, and keeps
only changes that improve results.

Instead of modifying train.py, we modify:
- Expansion prompts (how questions are generated)
- Scoring rubric weights (what matters most)
- Debate protocol parameters
- MCTS exploration constants

Metric: average composite score of top-10 questions per experiment window.
"""

import asyncio
import copy
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.llm_client import LLMClient

logger = logging.getLogger("deep-thought.autoresearch")


@dataclass
class ExperimentConfig:
    """The mutable parameters that autoresearch optimizes."""

    # Scoring rubric weights (must sum to 1.0)
    math_weight: float = 0.25
    philosophy_weight: float = 0.30
    humor_weight: float = 0.25
    universality_weight: float = 0.20

    # MCTS parameters
    exploration_constant: float = 1.414
    expand_count: int = 5

    # Debate parameters
    debate_rounds: int = 3
    max_proposer_tokens: int = 800
    max_opponent_tokens: int = 800
    proposer_temperature: float = 0.7
    opponent_temperature: float = 0.7

    # Expansion parameters
    expansion_temperature: float = 0.9
    expansion_prompt_suffix: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "ExperimentConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ExperimentResult:
    """Outcome of a single experiment window."""
    config: ExperimentConfig
    top_10_avg_score: float
    questions_generated: int
    debates_completed: int
    duration_seconds: float
    top_question: str
    top_score: float


HYPOTHESIS_SYSTEM = """You are an AI research scientist optimizing an autonomous question-generation
system. The system uses MCTS + adversarial debate to find the Ultimate Question of Life, the
Universe, and Everything (whose answer is 42).

You are given the current configuration parameters and recent experiment results.
Your job: propose ONE specific parameter change that might improve the average score.

RULES:
1. Change ONLY ONE parameter at a time (scientific method)
2. Make targeted changes based on evidence from past results
3. Weight changes must keep the sum at 1.0
4. Temperature changes should be small (0.05-0.15 increments)
5. Provide clear reasoning for your hypothesis

You MUST respond with ONLY valid JSON:
{
    "parameter": "<name of parameter to change>",
    "old_value": <current value>,
    "new_value": <proposed value>,
    "hypothesis": "<why this change should improve scores>",
    "evidence": "<what in the recent results suggests this>"
}"""


class AutoResearchLoop:
    """
    Karpathy-style autonomous experimentation loop.

    Runs experiments, proposes parameter changes, keeps improvements.
    """

    def __init__(
        self,
        reasoner_client: LLMClient,
        experiment_window_minutes: float = 10.0,
        log_dir: str = "logs/autoresearch",
    ):
        self.reasoner = reasoner_client
        self.window_minutes = experiment_window_minutes
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # State
        self.current_config = ExperimentConfig()
        self.best_config = ExperimentConfig()
        self.best_score = 0.0
        self.experiment_history: list[dict] = []
        self.experiment_count = 0
        self.improvements = 0
        self.rollbacks = 0

    async def propose_change(self, recent_results: list[ExperimentResult]) -> dict:
        """Use the LLM to propose a parameter change."""
        # Build context from recent experiments
        history_str = ""
        for i, result in enumerate(recent_results[-5:]):  # Last 5 experiments
            history_str += (
                f"\nExperiment {i + 1}:\n"
                f"  Config: {json.dumps(result.config.to_dict(), indent=2)}\n"
                f"  Top-10 Avg Score: {result.top_10_avg_score:.3f}\n"
                f"  Top Question: \"{result.top_question}\"\n"
                f"  Top Score: {result.top_score:.2f}\n"
                f"  Questions Generated: {result.questions_generated}\n"
                f"  Debates Completed: {result.debates_completed}\n"
            )

        prompt = (
            f"CURRENT CONFIGURATION:\n{json.dumps(self.current_config.to_dict(), indent=2)}\n\n"
            f"CURRENT BEST SCORE: {self.best_score:.3f}\n\n"
            f"RECENT EXPERIMENT HISTORY:{history_str}\n\n"
            f"EXPERIMENT COUNT: {self.experiment_count} "
            f"(improvements: {self.improvements}, rollbacks: {self.rollbacks})\n\n"
            f"Propose ONE parameter change to improve the top-10 average score."
        )

        response = await self.reasoner.generate(
            system=HYPOTHESIS_SYSTEM,
            prompt=prompt,
            max_tokens=400,
            temperature=0.7,
        )

        try:
            cleaned = response.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            start = cleaned.index("{")
            end = cleaned.rindex("}") + 1
            proposal = json.loads(cleaned[start:end])
            return proposal
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("[AUTORESEARCH] Failed to parse proposal: %s", e)
            return None

    def apply_change(self, proposal: dict) -> ExperimentConfig:
        """Apply a proposed change to create a new config."""
        new_config = copy.deepcopy(self.current_config)
        param = proposal.get("parameter", "")
        new_value = proposal.get("new_value")

        if not hasattr(new_config, param):
            logger.warning("[AUTORESEARCH] Unknown parameter: %s", param)
            return new_config

        # Validate weight changes
        if param.endswith("_weight"):
            # Adjust the changed weight and normalize
            setattr(new_config, param, new_value)
            total = (
                new_config.math_weight
                + new_config.philosophy_weight
                + new_config.humor_weight
                + new_config.universality_weight
            )
            if total > 0:
                new_config.math_weight /= total
                new_config.philosophy_weight /= total
                new_config.humor_weight /= total
                new_config.universality_weight /= total
        else:
            setattr(new_config, param, new_value)

        return new_config

    def evaluate_experiment(self, result: ExperimentResult) -> bool:
        """Compare result against best. Return True if improved."""
        improved = result.top_10_avg_score > self.best_score

        if improved:
            self.best_score = result.top_10_avg_score
            self.best_config = copy.deepcopy(result.config)
            self.improvements += 1
            logger.info(
                "[AUTORESEARCH] IMPROVEMENT! %.3f -> %.3f (+%.3f) | Keeping change",
                self.best_score - (result.top_10_avg_score - self.best_score),
                self.best_score,
                result.top_10_avg_score - (self.best_score - (result.top_10_avg_score - self.best_score)),
            )
        else:
            self.rollbacks += 1
            self.current_config = copy.deepcopy(self.best_config)
            logger.info(
                "[AUTORESEARCH] No improvement (%.3f <= %.3f). Rolling back.",
                result.top_10_avg_score, self.best_score,
            )

        # Log experiment
        self.experiment_count += 1
        record = {
            "experiment_id": self.experiment_count,
            "timestamp": time.time(),
            "config": result.config.to_dict(),
            "top_10_avg_score": result.top_10_avg_score,
            "top_question": result.top_question,
            "top_score": result.top_score,
            "improved": improved,
            "best_score": self.best_score,
        }
        self.experiment_history.append(record)

        # Persist to disk
        history_path = self.log_dir / "experiment_history.jsonl"
        with open(history_path, "a") as f:
            f.write(json.dumps(record) + "\n")

        return improved

    def get_summary(self) -> dict:
        """Return autoresearch loop statistics."""
        return {
            "experiment_count": self.experiment_count,
            "improvements": self.improvements,
            "rollbacks": self.rollbacks,
            "improvement_rate": self.improvements / max(1, self.experiment_count),
            "best_score": self.best_score,
            "best_config": self.best_config.to_dict(),
            "current_config": self.current_config.to_dict(),
        }

    def log_status(self):
        """Log current autoresearch status."""
        summary = self.get_summary()
        logger.info(
            "[AUTORESEARCH] Experiment #%d | Best: %.3f | Improvements: %d/%d (%.0f%%) | "
            "Current weights: math=%.2f phil=%.2f humor=%.2f univ=%.2f",
            summary["experiment_count"],
            summary["best_score"],
            summary["improvements"],
            summary["experiment_count"],
            summary["improvement_rate"] * 100,
            self.current_config.math_weight,
            self.current_config.philosophy_weight,
            self.current_config.humor_weight,
            self.current_config.universality_weight,
        )
