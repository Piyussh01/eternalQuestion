"""
Deep Thought 2.0 Orchestrator.

Runs a 24-hour perspective-generation and reasoning experiment to answer one fixed question:
"What is the meaning of life?"
"""

import asyncio
import json
import logging
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from src.autoresearch import AutoResearchLoop, ExperimentResult
from src.db import DB
from src.debate import ModelComparisonArena
from src.expander import AnswerGenerator
from src.llm_client import EXPLORER_CONFIG, REASONER_CONFIG, LLMClient
from src.logger_setup import setup_logging

logger = logging.getLogger("deep-thought")

TARGET_QUESTION = "What is the meaning of life?"


class Phase:
    WARMUP = "warmup"
    EXPLORATION = "exploration"
    REFINEMENT = "refinement"
    CONSENSUS = "consensus"
    FINAL_JUDGMENT = "final_judgment"


PHASE_CONFIG = {
    Phase.WARMUP: {"hours": (0, 1), "quick": True},
    Phase.EXPLORATION: {"hours": (1, 12), "quick": True},
    Phase.REFINEMENT: {"hours": (12, 20), "quick": False},
    Phase.CONSENSUS: {"hours": (20, 23), "quick": False},
    Phase.FINAL_JUDGMENT: {"hours": (23, 24), "quick": False},
}


class DeepThought:
    """24-hour answer search using perspective probes, dense reasoning, and conservative autoresearch."""

    def __init__(self, run_hours: float = 24.0):
        self.run_hours = run_hours
        self.start_time = 0.0
        self.running = True
        self.iteration = 0
        self.evaluations_completed = 0
        self.phase = Phase.WARMUP

        self.db: DB | None = None
        self.explorer_client: LLMClient | None = None
        self.reasoner_client: LLMClient | None = None
        self.explorer_generator: AnswerGenerator | None = None
        self.reasoner_generator: AnswerGenerator | None = None
        self.arena: ModelComparisonArena | None = None
        self.autoresearch: AutoResearchLoop | None = None

    def _get_phase(self) -> str:
        elapsed_hours = (time.time() - self.start_time) / 3600
        for phase, config in PHASE_CONFIG.items():
            start_h, end_h = config["hours"]
            if start_h <= elapsed_hours < end_h:
                return phase
        return Phase.FINAL_JUDGMENT

    def _elapsed_str(self) -> str:
        elapsed = time.time() - self.start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        return f"{hours:02d}:{minutes:02d}"

    async def start(self):
        setup_logging()
        self.start_time = time.time()
        end_time = datetime.now() + timedelta(hours=self.run_hours)

        logger.info("=" * 70)
        logger.info("  DEEP THOUGHT 2.0 — Meaning of Life")
        logger.info("  Target question: %s", TARGET_QUESTION)
        logger.info("  Target runtime: %.1f hours", self.run_hours)
        logger.info("  Estimated completion: %s", end_time.strftime("%Y-%m-%d %H:%M"))
        logger.info("=" * 70)

        self.db = DB()
        self.explorer_client = LLMClient(EXPLORER_CONFIG)
        self.reasoner_client = LLMClient(REASONER_CONFIG)

        explorer_ok = await self.explorer_client.health_check()
        reasoner_ok = await self.reasoner_client.health_check()
        logger.info("[SYSTEM] Explorer/E4B health: %s", "OK" if explorer_ok else "FAILED")
        logger.info("[SYSTEM] Reasoner/Dense health: %s", "OK" if reasoner_ok else "FAILED")
        if not explorer_ok or not reasoner_ok:
            logger.error("[SYSTEM] Model health check failed. Run: bash scripts/start_vllm.sh")
            sys.exit(1)

        self.explorer_generator = AnswerGenerator(self.explorer_client)
        self.reasoner_generator = AnswerGenerator(self.reasoner_client)
        self.arena = ModelComparisonArena(self.explorer_client, self.reasoner_client)
        self.autoresearch = AutoResearchLoop(self.reasoner_client)

        await self._seed_answers()

        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        try:
            await self._main_loop()
        except KeyboardInterrupt:
            logger.info("[SYSTEM] Keyboard interrupt received")
        finally:
            await self._final_report()
            await self._cleanup()

    async def _seed_answers(self):
        for answer in self.reasoner_generator.get_seed_answers():
            candidate_id = self.db.save_candidate(answer, REASONER_CONFIG.name, prompt_variant="seed")
            await self._evaluate_candidate(candidate_id, answer, REASONER_CONFIG.name, quick=True)

    async def _main_loop(self):
        last_leaderboard_time = time.time()
        last_stats_time = time.time()
        last_autoresearch_time = time.time()

        while self.running:
            elapsed_hours = (time.time() - self.start_time) / 3600
            if elapsed_hours >= self.run_hours:
                break

            new_phase = self._get_phase()
            if new_phase != self.phase:
                logger.info("[PHASE] %s -> %s at %s", self.phase, new_phase, self._elapsed_str())
                self.phase = new_phase

            if self.phase == Phase.FINAL_JUDGMENT:
                await self._final_judgment()
                break

            try:
                await self._iteration(PHASE_CONFIG[self.phase]["quick"])
                self.iteration += 1
            except Exception as e:
                logger.error("[SYSTEM] Iteration %d failed: %s", self.iteration, e, exc_info=True)
                await asyncio.sleep(5)

            if time.time() - last_autoresearch_time > 1800:
                await self._autoresearch_window()
                last_autoresearch_time = time.time()

            if time.time() - last_leaderboard_time > 1800:
                self._log_leaderboard()
                last_leaderboard_time = time.time()

            if time.time() - last_stats_time > 300:
                self._log_stats()
                last_stats_time = time.time()

    async def _iteration(self, quick: bool):
        config = self.autoresearch.current_config
        leaderboard = self.db.get_candidate_leaderboard(top_n=5)
        context = "\n".join(
            f"- {entry['answer']} (score: {entry['avg_score']:.1f}, source: {entry['source_model']})"
            for entry in leaderboard
        )
        theme = leaderboard[0]["answer"] if leaderboard else TARGET_QUESTION

        logger.info(
            "[ITER %d | %s | %s] Generating perspectives, then reasoned answers",
            self.iteration,
            self.phase,
            self._elapsed_str(),
        )

        perspectives = await self.explorer_generator.generate_perspectives(
            seed=theme,
            count=config.perspectives_per_cycle,
            context=context,
            prompt_suffix=config.generation_prompt_suffix,
            temperature=config.explorer_temperature,
        )

        for perspective in perspectives:
            answers = await self.reasoner_generator.generate_answers(
                perspective_question=perspective,
                count=config.answers_per_perspective,
                context=context,
                prompt_suffix=config.generation_prompt_suffix,
                temperature=config.reasoner_temperature,
            )
            for answer in answers:
                candidate_id = self.db.save_candidate(
                    answer,
                    REASONER_CONFIG.name,
                    parent_answer=theme,
                    prompt_variant=perspective,
                )
                await self._evaluate_candidate(candidate_id, answer, REASONER_CONFIG.name, quick=quick)

    async def _evaluate_candidate(self, candidate_id: int, answer: str, source_model: str, quick: bool):
        result = await self.arena.evaluate_answer(answer, source_model, quick=quick)
        self.db.save_candidate_evaluation(
            candidate_id=candidate_id,
            evaluator_model=result.advocate_model,
            opponent_model=result.critic_model,
            rounds=result.rounds,
            transcript={
                "advocate": result.advocate_arguments,
                "critic": result.critic_arguments,
                "duration_seconds": result.duration_seconds,
            },
            scores=result.scores,
            composite_score=result.composite_score,
            judge_reasoning=result.judge_reasoning,
            config=self.autoresearch.current_config.to_dict(),
        )
        self.evaluations_completed += 1

    async def _autoresearch_window(self):
        leaderboard = self.db.get_candidate_leaderboard(top_n=10)
        if not leaderboard:
            return

        result = ExperimentResult(
            config=self.autoresearch.current_config,
            top_10_avg_score=sum(x["avg_score"] for x in leaderboard) / len(leaderboard),
            answers_generated=self.db.get_candidate_stats()["candidates"],
            evaluations_completed=self.evaluations_completed,
            duration_seconds=time.time() - self.start_time,
            top_answer=leaderboard[0]["answer"],
            top_score=leaderboard[0]["avg_score"],
        )
        self.autoresearch.evaluate_experiment(result)
        proposal = await self.autoresearch.propose_change([result])
        if proposal:
            self.autoresearch.current_config = self.autoresearch.apply_change(proposal)
            logger.info("[AUTORESEARCH] Trying proposal: %s", proposal)
        self.autoresearch.log_status()

    async def _final_judgment(self):
        logger.info("=" * 70)
        logger.info("  FINAL JUDGMENT — Re-evaluating top answers")
        logger.info("=" * 70)
        for entry in self.db.get_candidate_leaderboard(top_n=8):
            await self._evaluate_candidate(entry["id"], entry["answer"], entry["source_model"], quick=False)

    def _log_leaderboard(self):
        logger.info("[LEADER] === Current Top Answers (elapsed: %s) ===", self._elapsed_str())
        for entry in self.db.get_candidate_leaderboard(top_n=10):
            logger.info(
                "[LEADER] #%d %.2f %s: %s",
                entry["rank"],
                entry["avg_score"],
                entry["source_model"],
                entry["answer"][:120],
            )

    def _log_stats(self):
        stats = self.db.get_candidate_stats()
        explorer_stats = self.explorer_client.get_stats()
        reasoner_stats = self.reasoner_client.get_stats()
        logger.info(
            "[SYSTEM] Stats %s | candidates=%d evaluations=%d avg=%.2f by_model=%s | "
            "explorer=%d req/%d tok reasoner=%d req/%d tok",
            self._elapsed_str(),
            stats["candidates"],
            stats["evaluations"],
            stats["avg_score"],
            stats["by_model"],
            explorer_stats.get("requests", 0),
            explorer_stats.get("total_tokens", 0),
            reasoner_stats.get("requests", 0),
            reasoner_stats.get("total_tokens", 0),
        )

    async def _final_report(self):
        if not self.db:
            return
        leaderboard = self.db.get_candidate_leaderboard(top_n=50)
        report = {
            "target_question": TARGET_QUESTION,
            "run_duration_hours": (time.time() - self.start_time) / 3600,
            "total_iterations": self.iteration,
            "total_evaluations": self.evaluations_completed,
            "candidate_stats": self.db.get_candidate_stats(),
            "top_answers": leaderboard,
            "autoresearch": self.autoresearch.get_summary() if self.autoresearch else {},
            "explorer_stats": self.explorer_client.get_stats() if self.explorer_client else {},
            "reasoner_stats": self.reasoner_client.get_stats() if self.reasoner_client else {},
        }
        report_path = Path("logs/run_report.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2))

        final_path = Path("logs/final_results.json")
        final_path.write_text(json.dumps(leaderboard[:10], indent=2))

        logger.info("=" * 70)
        logger.info("  RUN COMPLETE")
        if leaderboard:
            logger.info("  BEST ANSWER: %s", leaderboard[0]["answer"])
            logger.info("  SCORE: %.2f", leaderboard[0]["avg_score"])
        logger.info("  Report: %s", report_path)
        logger.info("=" * 70)

    async def _cleanup(self):
        if self.explorer_client:
            await self.explorer_client.close()
        if self.reasoner_client:
            await self.reasoner_client.close()
        if self.db:
            self.db.close()

    def _handle_shutdown(self, signum, frame):
        logger.info("[SYSTEM] Shutdown signal received (%s). Finishing current iteration...", signum)
        self.running = False


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Deep Thought 2.0 — Meaning of Life")
    parser.add_argument("--hours", type=float, default=24.0, help="Run duration in hours")
    args = parser.parse_args()

    deep_thought = DeepThought(run_hours=args.hours)
    await deep_thought.start()


if __name__ == "__main__":
    asyncio.run(main())
