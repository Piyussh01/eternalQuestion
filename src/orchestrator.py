"""
Deep Thought 2.0 Orchestrator

The main loop that runs for 24 hours:
1. MCTS Select -> Expand -> Debate -> Backpropagate
2. Phase transitions (exploration -> exploitation -> convergence)
3. Periodic logging, leaderboard updates, skill refinement
"""

import asyncio
import json
import logging
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from src.mcts import MCTSTree
from src.debate import DebateArena
from src.expander import QuestionExpander
from src.llm_client import LLMClient, EXPLORER_CONFIG, REASONER_CONFIG
from src.logger_setup import setup_logging

logger = logging.getLogger("deep-thought")


class Phase:
    WARMUP = "warmup"
    EXPLORATION = "exploration"
    EXPLOITATION = "exploitation"
    CONVERGENCE = "convergence"
    FINAL_JUDGMENT = "final_judgment"


PHASE_CONFIG = {
    Phase.WARMUP:        {"hours": (0, 1),   "C": 2.0, "expand_count": 5, "quick_debate": True},
    Phase.EXPLORATION:   {"hours": (1, 8),   "C": 2.0, "expand_count": 5, "quick_debate": True},
    Phase.EXPLOITATION:  {"hours": (8, 16),  "C": 1.0, "expand_count": 3, "quick_debate": False},
    Phase.CONVERGENCE:   {"hours": (16, 23), "C": 0.5, "expand_count": 2, "quick_debate": False},
    Phase.FINAL_JUDGMENT: {"hours": (23, 24), "C": 0.0, "expand_count": 0, "quick_debate": False},
}


class DeepThought:
    """The main orchestrator. 24-hour autonomous MCTS + Debate."""

    def __init__(self, run_hours: float = 24.0):
        self.run_hours = run_hours
        self.start_time = None
        self.running = True

        # Components — initialized in start()
        self.tree: MCTSTree | None = None
        self.explorer_client: LLMClient | None = None
        self.reasoner_client: LLMClient | None = None
        self.expander: QuestionExpander | None = None
        self.arena: DebateArena | None = None

        # Stats
        self.iteration = 0
        self.phase = Phase.WARMUP
        self.debates_completed = 0

    def _get_phase(self) -> str:
        """Determine current phase based on elapsed time."""
        elapsed_hours = (time.time() - self.start_time) / 3600
        for phase, config in PHASE_CONFIG.items():
            start_h, end_h = config["hours"]
            if start_h <= elapsed_hours < end_h:
                return phase
        return Phase.FINAL_JUDGMENT

    def _get_phase_config(self) -> dict:
        return PHASE_CONFIG[self.phase]

    def _elapsed_str(self) -> str:
        elapsed = time.time() - self.start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        return f"{hours:02d}:{minutes:02d}"

    async def start(self):
        """Initialize components and begin the 24-hour run."""
        setup_logging()
        self.start_time = time.time()
        end_time = datetime.now() + timedelta(hours=self.run_hours)

        logger.info("=" * 70)
        logger.info("  DEEP THOUGHT 2.0 — The Eternal Question")
        logger.info("  Target runtime: %.1f hours", self.run_hours)
        logger.info("  Estimated completion: %s", end_time.strftime("%Y-%m-%d %H:%M"))
        logger.info("=" * 70)

        # Initialize tree
        self.tree = MCTSTree()
        logger.info("[SYSTEM] MCTS tree initialized: %s", self.tree.db_path)

        # Initialize LLM clients
        self.explorer_client = LLMClient(EXPLORER_CONFIG)
        self.reasoner_client = LLMClient(REASONER_CONFIG)

        # Health check
        explorer_ok = await self.explorer_client.health_check()
        reasoner_ok = await self.reasoner_client.health_check()
        logger.info("[SYSTEM] Explorer (26B MoE) health: %s", "OK" if explorer_ok else "FAILED")
        logger.info("[SYSTEM] Reasoner (31B Dense) health: %s", "OK" if reasoner_ok else "FAILED")

        if not explorer_ok or not reasoner_ok:
            logger.error("[SYSTEM] Model health check failed. Ensure vLLM is running.")
            logger.error("[SYSTEM] Expected: explorer at %s, reasoner at %s",
                         EXPLORER_CONFIG.base_url, REASONER_CONFIG.base_url)
            sys.exit(1)

        # Initialize expander and arena
        self.expander = QuestionExpander(self.explorer_client)
        self.arena = DebateArena(self.reasoner_client)

        # Seed the tree
        await self._seed_tree()

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        # Main loop
        try:
            await self._main_loop()
        except KeyboardInterrupt:
            logger.info("[SYSTEM] Keyboard interrupt received")
        finally:
            await self._final_report()
            await self._cleanup()

    async def _seed_tree(self):
        """Populate tree with initial seed questions."""
        root = self.tree.get_root()
        seeds = self.expander.get_seed_questions()
        self.tree.expand(root.id, seeds)
        logger.info("[MCTS] Seeded tree with %d initial questions", len(seeds))

    async def _main_loop(self):
        """The core 24-hour loop."""
        last_leaderboard_time = time.time()
        last_stats_time = time.time()

        while self.running:
            # Check time budget
            elapsed_hours = (time.time() - self.start_time) / 3600
            if elapsed_hours >= self.run_hours:
                logger.info("[SYSTEM] Time budget exhausted (%.1f hours). Entering final judgment.",
                            elapsed_hours)
                break

            # Update phase
            new_phase = self._get_phase()
            if new_phase != self.phase:
                logger.info("=" * 50)
                logger.info("[PHASE] Transitioning: %s -> %s (elapsed: %s)",
                            self.phase, new_phase, self._elapsed_str())
                logger.info("=" * 50)
                self.phase = new_phase

            config = self._get_phase_config()

            # Final judgment phase: run tournament
            if self.phase == Phase.FINAL_JUDGMENT:
                await self._final_tournament()
                break

            # Core MCTS iteration
            try:
                await self._mcts_iteration(config)
                self.iteration += 1
            except Exception as e:
                logger.error("[SYSTEM] Iteration %d failed: %s", self.iteration, e, exc_info=True)
                await asyncio.sleep(5)  # Brief pause before retry
                continue

            # Periodic leaderboard (every 30 minutes)
            if time.time() - last_leaderboard_time > 1800:
                self._log_leaderboard()
                self.tree.record_stats(self.phase, config["C"])
                last_leaderboard_time = time.time()

            # Periodic stats (every 5 minutes)
            if time.time() - last_stats_time > 300:
                self._log_stats()
                last_stats_time = time.time()

    async def _mcts_iteration(self, config: dict):
        """Single MCTS iteration: Select -> Expand -> Debate -> Backpropagate."""
        logger.info(
            "[ITER %d | %s | %s] Starting iteration (C=%.1f)",
            self.iteration, self.phase, self._elapsed_str(), config["C"],
        )

        # 1. SELECT
        node = self.tree.select(exploration_constant=config["C"])

        # 2. EXPAND (if not in convergence with expand_count=0)
        if config["expand_count"] > 0 and node.visits > 0:
            # Build context from top-scoring questions
            leaderboard = self.tree.get_leaderboard(top_n=5)
            context = "\n".join(
                f"- \"{entry['question']}\" (score: {entry['avg_score']:.1f})"
                for entry in leaderboard
            ) if leaderboard else ""

            new_questions = await self.expander.expand(
                parent_question=node.question,
                count=config["expand_count"],
                context=context,
            )
            if new_questions:
                children = self.tree.expand(node.id, new_questions)
                # Debate the first new child
                node = children[0]
            else:
                logger.warning("[MCTS] Expansion returned no questions, debating selected node")

        # 3. SIMULATE (Debate)
        if node.id != self.tree.get_root().id:
            debate_result = await self.arena.run_debate(
                question=node.question,
                quick=config["quick_debate"],
            )

            # 4. BACKPROPAGATE
            self.tree.backpropagate(node.id, debate_result.scores)
            self.tree.record_debate(node.id, {
                "proposer": "\n---\n".join(debate_result.proposer_arguments),
                "opponent": "\n---\n".join(debate_result.opponent_arguments),
                "judge_reasoning": debate_result.judge_reasoning,
                **debate_result.scores,
                "composite": debate_result.composite_score,
            })
            self.debates_completed += 1

            logger.info(
                "[ITER %d] Completed: \"%s\" -> composite=%.2f",
                self.iteration, node.question[:60], debate_result.composite_score,
            )

    async def _final_tournament(self):
        """Final hour: top 8 candidates debate head-to-head."""
        logger.info("=" * 70)
        logger.info("  FINAL TOURNAMENT — Top candidates debate head-to-head")
        logger.info("=" * 70)

        leaderboard = self.tree.get_leaderboard(top_n=8)
        if not leaderboard:
            logger.warning("[TOURNAMENT] No candidates to rank!")
            return

        # Re-evaluate top 8 with full 3-round debates
        final_scores = []
        for entry in leaderboard:
            logger.info("[TOURNAMENT] Re-evaluating: %s", entry["question"][:80])
            result = await self.arena.run_debate(
                question=entry["question"],
                quick=False,
            )
            self.tree.backpropagate(entry["id"], result.scores)
            final_scores.append({
                "question": entry["question"],
                "final_composite": result.composite_score,
                "scores": result.scores,
                "judge_reasoning": result.judge_reasoning,
            })

        # Sort by final composite
        final_scores.sort(key=lambda x: x["final_composite"], reverse=True)

        logger.info("=" * 70)
        logger.info("  FINAL RESULTS — The Ultimate Question Candidates")
        logger.info("=" * 70)
        for i, entry in enumerate(final_scores):
            logger.info(
                "  #%d (%.2f): %s",
                i + 1, entry["final_composite"], entry["question"],
            )
            logger.info(
                "       math=%.0f phil=%.0f humor=%.0f univ=%.0f",
                entry["scores"]["math"], entry["scores"]["philosophy"],
                entry["scores"]["humor"], entry["scores"]["universality"],
            )
            logger.info("       Judge: %s", entry.get("judge_reasoning", "")[:200])
        logger.info("=" * 70)

        # Save final report
        report_path = Path("logs/final_results.json")
        report_path.write_text(json.dumps(final_scores, indent=2))
        logger.info("[SYSTEM] Final results saved to %s", report_path)

    def _log_leaderboard(self):
        """Log current top 10."""
        leaderboard = self.tree.get_leaderboard(top_n=10)
        logger.info("[LEADER] === Current Top 10 (elapsed: %s) ===", self._elapsed_str())
        for entry in leaderboard:
            logger.info(
                "[LEADER] #%d (%.2f, %d visits): %s",
                entry["rank"], entry["avg_score"], entry["visits"],
                entry["question"][:80],
            )

    def _log_stats(self):
        """Log aggregate statistics."""
        stats = self.tree.get_tree_stats()
        explorer_stats = self.expander.get_stats() if self.expander else {}
        explorer_llm = self.explorer_client.get_stats() if self.explorer_client else {}
        reasoner_llm = self.reasoner_client.get_stats() if self.reasoner_client else {}

        logger.info(
            "[SYSTEM] Stats (elapsed: %s) | nodes=%d visited=%d depth=%d debates=%d | "
            "explorer: %d reqs %d tok | reasoner: %d reqs %d tok",
            self._elapsed_str(),
            stats["total_nodes"], stats["visited_nodes"],
            stats["max_depth"], stats["total_debates"],
            explorer_llm.get("requests", 0), explorer_llm.get("total_tokens", 0),
            reasoner_llm.get("requests", 0), reasoner_llm.get("total_tokens", 0),
        )

    async def _final_report(self):
        """Generate the final report at shutdown."""
        if not self.tree:
            return

        stats = self.tree.get_tree_stats()
        leaderboard = self.tree.get_leaderboard(top_n=50)
        elapsed = time.time() - self.start_time

        report = {
            "run_duration_hours": elapsed / 3600,
            "total_iterations": self.iteration,
            "total_debates": self.debates_completed,
            "tree_stats": stats,
            "top_50_questions": leaderboard,
            "explorer_stats": self.explorer_client.get_stats() if self.explorer_client else {},
            "reasoner_stats": self.reasoner_client.get_stats() if self.reasoner_client else {},
        }

        report_path = Path("logs/run_report.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2))

        logger.info("=" * 70)
        logger.info("  DEEP THOUGHT 2.0 — RUN COMPLETE")
        logger.info("  Duration: %.1f hours", elapsed / 3600)
        logger.info("  Iterations: %d", self.iteration)
        logger.info("  Debates: %d", self.debates_completed)
        logger.info("  Tree nodes: %d", stats["total_nodes"])
        logger.info("  Max depth: %d", stats["max_depth"])
        if leaderboard:
            logger.info("  TOP ANSWER: \"%s\" (score: %.2f)",
                        leaderboard[0]["question"], leaderboard[0]["avg_score"])
        logger.info("  Report: %s", report_path)
        logger.info("=" * 70)

    async def _cleanup(self):
        """Close all connections."""
        if self.explorer_client:
            await self.explorer_client.close()
        if self.reasoner_client:
            await self.reasoner_client.close()
        if self.tree:
            self.tree.close()

    def _handle_shutdown(self, signum, frame):
        logger.info("[SYSTEM] Shutdown signal received (%s). Finishing current iteration...", signum)
        self.running = False


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Deep Thought 2.0 — The Eternal Question")
    parser.add_argument("--hours", type=float, default=24.0, help="Run duration in hours")
    args = parser.parse_args()

    deep_thought = DeepThought(run_hours=args.hours)
    await deep_thought.start()


if __name__ == "__main__":
    asyncio.run(main())
