"""
Conservative AutoResearch for the 24-hour meaning-of-life experiment.

This is an experiment scheduler, not an aggressive hill-climber. It proposes
small process changes, runs them for a window, and only promotes a config after
repeated evidence.
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

    # Perspective and candidate generation
    perspectives_per_cycle: int = 5
    answers_per_perspective: int = 2

    # Model comparison
    comparison_rounds: int = 2

    # Generation parameters
    explorer_temperature: float = 0.9
    reasoner_temperature: float = 0.65
    generation_prompt_suffix: str = ""

    # Promotion gate
    promotion_margin: float = 0.3
    required_wins: int = 3

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
    answers_generated: int
    evaluations_completed: int
    duration_seconds: float
    top_answer: str
    top_score: float


HYPOTHESIS_SYSTEM = """You are an AI research scientist optimizing a 24-hour experiment that tries
to answer exactly one question: "What is the meaning of life?"

You are given the current configuration parameters and recent experiment results.
Your job: propose ONE small process change that might improve candidate answer quality.

RULES:
1. Change ONLY ONE parameter at a time (scientific method)
2. Make targeted changes based on evidence from past results
3. Do not change the target question
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
        self.pending_wins = 0
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
                f"  Top Answer: \"{result.top_answer}\"\n"
                f"  Top Score: {result.top_score:.2f}\n"
                f"  Answers Generated: {result.answers_generated}\n"
                f"  Evaluations Completed: {result.evaluations_completed}\n"
            )

        prompt = (
            f"CURRENT CONFIGURATION:\n{json.dumps(self.current_config.to_dict(), indent=2)}\n\n"
            f"CURRENT BEST SCORE: {self.best_score:.3f}\n\n"
            f"RECENT EXPERIMENT HISTORY:{history_str}\n\n"
            f"EXPERIMENT COUNT: {self.experiment_count} "
            f"(improvements: {self.improvements}, rollbacks: {self.rollbacks})\n\n"
            f"Propose ONE parameter change to improve answer quality."
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

        setattr(new_config, param, new_value)
        self._clamp_config(new_config)

        return new_config

    def _clamp_config(self, config: ExperimentConfig) -> None:
        config.perspectives_per_cycle = int(max(1, min(12, config.perspectives_per_cycle)))
        config.answers_per_perspective = int(max(1, min(4, config.answers_per_perspective)))
        config.comparison_rounds = int(max(1, min(4, config.comparison_rounds)))
        config.explorer_temperature = max(0.2, min(1.2, float(config.explorer_temperature)))
        config.reasoner_temperature = max(0.2, min(1.0, float(config.reasoner_temperature)))
        config.promotion_margin = max(0.0, min(2.0, float(config.promotion_margin)))
        config.required_wins = int(max(1, min(5, config.required_wins)))

    def evaluate_experiment(self, result: ExperimentResult) -> bool:
        """Compare result against best. Return True if improved."""
        previous_best = self.best_score
        improved = result.top_10_avg_score >= self.best_score + self.current_config.promotion_margin

        if improved:
            self.pending_wins += 1
            if self.pending_wins >= self.current_config.required_wins:
                self.best_score = result.top_10_avg_score
                self.best_config = copy.deepcopy(result.config)
                self.current_config = copy.deepcopy(result.config)
                self.improvements += 1
                self.pending_wins = 0
                logger.info(
                    "[AUTORESEARCH] PROMOTED config %.3f -> %.3f (+%.3f)",
                    previous_best,
                    self.best_score,
                    self.best_score - previous_best,
                )
            else:
                logger.info(
                    "[AUTORESEARCH] Win %d/%d for candidate config (score %.3f, best %.3f)",
                    self.pending_wins,
                    self.current_config.required_wins,
                    result.top_10_avg_score,
                    self.best_score,
                )
        else:
            self.rollbacks += 1
            self.pending_wins = 0
            self.current_config = copy.deepcopy(self.best_config)
            logger.info(
                "[AUTORESEARCH] No improvement (%.3f <= %.3f). Rolling back.",
                result.top_10_avg_score, self.best_score + self.current_config.promotion_margin,
            )

        # Log experiment
        self.experiment_count += 1
        record = {
            "experiment_id": self.experiment_count,
            "timestamp": time.time(),
            "config": result.config.to_dict(),
            "top_10_avg_score": result.top_10_avg_score,
            "top_answer": result.top_answer,
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
            "pending_wins": self.pending_wins,
        }

    def log_status(self):
        """Log current autoresearch status."""
        summary = self.get_summary()
        logger.info(
            "[AUTORESEARCH] Experiment #%d | Best: %.3f | Improvements: %d/%d (%.0f%%) | "
            "Config: perspectives=%d answers/perspective=%d rounds=%d temps=(%.2f, %.2f)",
            summary["experiment_count"],
            summary["best_score"],
            summary["improvements"],
            summary["experiment_count"],
            summary["improvement_rate"] * 100,
            self.current_config.perspectives_per_cycle,
            self.current_config.answers_per_perspective,
            self.current_config.comparison_rounds,
            self.current_config.explorer_temperature,
            self.current_config.reasoner_temperature,
        )
