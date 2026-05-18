"""
Adversarial Debate Engine for the Ultimate Question.

Two agents (Proposer + Opponent) argue for/against a candidate question.
A Judge agent scores the debate on 4 axes.
"""

import json
import logging
import time
from dataclasses import dataclass

from src.llm_client import LLMClient

logger = logging.getLogger("deep-thought.debate")

PROPOSER_SYSTEM = """You are the Proposer in a philosophical debate about the Ultimate Question.

CONTEXT: In Douglas Adams' Hitchhiker's Guide to the Galaxy, the supercomputer Deep Thought
determined that the Answer to the Ultimate Question of Life, the Universe, and Everything is 42.
But the Question itself was never found. You must argue that the given candidate question IS
the Ultimate Question whose answer is 42.

Your argument should address:
1. How the answer to this question could be 42 (literally, metaphorically, or mathematically)
2. Why this question captures the essence of life, the universe, and everything
3. Why Douglas Adams would find this satisfyingly absurd
4. Why any conscious being would eventually ask this question

Be creative, philosophical, and occasionally witty. Channel both deep thought and British humor."""

OPPONENT_SYSTEM = """You are the Opponent in a philosophical debate about the Ultimate Question.

CONTEXT: In Douglas Adams' Hitchhiker's Guide to the Galaxy, the Answer is 42, but the Question
was never found. You must argue that the given candidate question is NOT the Ultimate Question.

Your argument should address:
1. Why the answer to this question is NOT naturally 42
2. Why this question fails to capture life, the universe, and everything
3. Why Douglas Adams would NOT find this satisfying
4. Why this question is too specific, too vague, too obvious, or otherwise wrong

Be sharp, incisive, and occasionally devastating. A good opponent makes the Proposer's job harder,
which produces better candidates through selection pressure."""

JUDGE_SYSTEM = """You are the Judge evaluating a debate about whether a candidate question is
the Ultimate Question of Life, the Universe, and Everything (whose answer is 42).

After reading the debate, you must score the candidate question on exactly 4 axes.
Each score is 0-10 (integers only).

You MUST respond with ONLY valid JSON in this exact format:
{
    "math": <0-10>,
    "philosophy": <0-10>,
    "humor": <0-10>,
    "universality": <0-10>,
    "reasoning": "<2-3 sentence explanation of your scoring>"
}

Scoring guide:
- math: Does the question naturally produce 42 as an answer? (literal, mathematical, or through
  clever interpretation). Score 10 if 42 is the only natural answer. Score 0 if 42 is impossible.
- philosophy: Does this question genuinely grapple with the meaning of life, the universe,
  and everything? Score 10 for profound existential questions. Score 0 for trivial questions.
- humor: Would Douglas Adams approve? The best score goes to questions that are simultaneously
  profound AND absurd — the humor comes from the gap between the depth of the question and the
  banality of the answer 42. Score 0 for questions that are either too serious or too silly.
- universality: Would all conscious beings (human, alien, AI) eventually ask this question?
  Score 10 for truly universal questions. Score 0 for culturally specific ones.

Be a rigorous but fair judge. Do not inflate scores."""


@dataclass
class DebateResult:
    question: str
    proposer_arguments: list[str]
    opponent_arguments: list[str]
    judge_reasoning: str
    scores: dict[str, float]
    composite_score: float
    rounds: int
    duration_seconds: float


class DebateArena:
    """Runs structured debates about candidate questions."""

    def __init__(
        self,
        reasoning_client: LLMClient,
        rounds: int = 3,
    ):
        self.reasoning_client = reasoning_client
        self.rounds = rounds

    async def run_debate(self, question: str, quick: bool = False) -> DebateResult:
        """Run a full debate about a candidate question."""
        start = time.time()
        actual_rounds = 1 if quick else self.rounds
        proposer_args = []
        opponent_args = []

        logger.info("[DEBATE] Starting %s debate on: %s",
                     "quick" if quick else f"{actual_rounds}-round", question[:80])

        # Build debate history incrementally
        debate_history = f"CANDIDATE QUESTION: \"{question}\"\n\n"

        for round_num in range(1, actual_rounds + 1):
            # Proposer turn
            proposer_prompt = f"{debate_history}---\nRound {round_num}/{actual_rounds}. "
            if round_num == 1:
                proposer_prompt += f"Make your opening argument for why \"{question}\" is the Ultimate Question whose answer is 42."
            else:
                proposer_prompt += f"Respond to the opponent's argument. Strengthen your case."

            proposer_response = await self.reasoning_client.generate(
                system=PROPOSER_SYSTEM,
                prompt=proposer_prompt,
                max_tokens=800,
            )
            proposer_args.append(proposer_response)
            debate_history += f"PROPOSER (Round {round_num}): {proposer_response}\n\n"

            logger.info("[DEBATE] Round %d/%d Proposer done (%d chars)",
                        round_num, actual_rounds, len(proposer_response))

            # Opponent turn
            opponent_prompt = f"{debate_history}---\nRound {round_num}/{actual_rounds}. "
            if round_num == 1:
                opponent_prompt += f"Counter the proposer's argument. Explain why \"{question}\" is NOT the Ultimate Question."
            else:
                opponent_prompt += "Counter the proposer's latest argument. Find weaknesses."

            opponent_response = await self.reasoning_client.generate(
                system=OPPONENT_SYSTEM,
                prompt=opponent_prompt,
                max_tokens=800,
            )
            opponent_args.append(opponent_response)
            debate_history += f"OPPONENT (Round {round_num}): {opponent_response}\n\n"

            logger.info("[DEBATE] Round %d/%d Opponent done (%d chars)",
                        round_num, actual_rounds, len(opponent_response))

        # Judge evaluation
        judge_prompt = (
            f"{debate_history}---\n"
            f"The debate is over. Score the candidate question \"{question}\" "
            f"based on the arguments presented. Respond with ONLY valid JSON."
        )

        judge_response = await self.reasoning_client.generate(
            system=JUDGE_SYSTEM,
            prompt=judge_prompt,
            max_tokens=400,
        )

        scores = self._parse_judge_response(judge_response)
        composite = (
            0.25 * scores["math"]
            + 0.30 * scores["philosophy"]
            + 0.25 * scores["humor"]
            + 0.20 * scores["universality"]
        )

        duration = time.time() - start

        logger.info(
            "[JUDGE] Scored \"%s\": math=%.0f phil=%.0f humor=%.0f univ=%.0f composite=%.2f (%.1fs)",
            question[:60], scores["math"], scores["philosophy"],
            scores["humor"], scores["universality"], composite, duration,
        )

        return DebateResult(
            question=question,
            proposer_arguments=proposer_args,
            opponent_arguments=opponent_args,
            judge_reasoning=scores.get("reasoning", ""),
            scores={k: v for k, v in scores.items() if k != "reasoning"},
            composite_score=composite,
            rounds=actual_rounds,
            duration_seconds=duration,
        )

    def _parse_judge_response(self, response: str) -> dict:
        """Extract scores from judge's JSON response."""
        # Try to find JSON in the response
        try:
            # Handle cases where judge wraps JSON in markdown code blocks
            cleaned = response.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()

            # Find the JSON object
            start = cleaned.index("{")
            end = cleaned.rindex("}") + 1
            data = json.loads(cleaned[start:end])

            return {
                "math": max(0, min(10, float(data.get("math", 0)))),
                "philosophy": max(0, min(10, float(data.get("philosophy", 0)))),
                "humor": max(0, min(10, float(data.get("humor", 0)))),
                "universality": max(0, min(10, float(data.get("universality", 0)))),
                "reasoning": data.get("reasoning", ""),
            }
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning("[JUDGE] Failed to parse judge response: %s", e)
            logger.warning("[JUDGE] Raw response: %s", response[:500])
            return {
                "math": 3.0,
                "philosophy": 3.0,
                "humor": 3.0,
                "universality": 3.0,
                "reasoning": f"Parse error, default scores assigned: {e}",
            }
