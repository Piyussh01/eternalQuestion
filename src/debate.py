"""
Model comparison for candidate answers to the meaning of life.
"""

import json
import logging
import time
from dataclasses import dataclass

from src.llm_client import LLMClient

logger = logging.getLogger("deep-thought.debate")


@dataclass
class ComparisonResult:
    answer: str
    source_model: str
    advocate_model: str
    critic_model: str
    advocate_arguments: list[str]
    critic_arguments: list[str]
    judge_reasoning: str
    scores: dict[str, float]
    composite_score: float
    rounds: int
    duration_seconds: float


ANSWER_ADVOCATE_SYSTEM = """You are defending a candidate answer to the question:
"What is the meaning of life?"

Argue that the candidate answer is sufficient: nothing more and nothing less.
Address practical usefulness, philosophical depth, universality, and whether it remains
clear under pressure. Do not change the answer; defend it."""

ANSWER_CRITIC_SYSTEM = """You are stress-testing a candidate answer to the question:
"What is the meaning of life?"

Attack weak assumptions, vagueness, false universality, sentimental filler, and anything
that goes beyond or falls short of answering the question. Be rigorous and concise."""

ANSWER_JUDGE_SYSTEM = """You are judging a candidate answer to the question:
"What is the meaning of life?"

Score the answer on exactly 4 axes. Each score is 0-10.

You MUST respond with ONLY valid JSON in this exact format:
{
    "directness": <0-10>,
    "depth": <0-10>,
    "universality": <0-10>,
    "resilience": <0-10>,
    "reasoning": "<2-3 sentence explanation>"
}

Scoring guide:
- directness: Does it answer the meaning of life, nothing more and nothing less?
- depth: Does it carry real philosophical weight without padding?
- universality: Could many kinds of conscious beings recognize it?
- resilience: Does it survive the critic's objections?

Do not reward ornate language. Reward answers that remain true, useful, and complete."""


class ModelComparisonArena:
    """Compares model contributions on candidate answers."""

    def __init__(
        self,
        explorer_client: LLMClient,
        reasoner_client: LLMClient,
        rounds: int = 2,
    ):
        self.clients = {
            explorer_client.config.name: explorer_client,
            reasoner_client.config.name: reasoner_client,
        }
        self.judge_client = reasoner_client
        self.rounds = rounds

    async def evaluate_answer(
        self,
        answer: str,
        source_model: str,
        quick: bool = False,
    ) -> ComparisonResult:
        start = time.time()
        actual_rounds = 1 if quick else self.rounds
        advocate_client = self.clients[source_model]
        critic_model = next(name for name in self.clients if name != source_model)
        critic_client = self.clients[critic_model]

        advocate_args = []
        critic_args = []
        transcript = f'CANDIDATE ANSWER: "{answer}"\n\n'

        logger.info("[COMPARE] %s defends, %s critiques: %s", source_model, critic_model, answer[:80])

        for round_num in range(1, actual_rounds + 1):
            advocate_response = await advocate_client.generate(
                system=ANSWER_ADVOCATE_SYSTEM,
                prompt=(
                    f"{transcript}---\nRound {round_num}/{actual_rounds}. "
                    "Defend this as the answer to the meaning of life."
                ),
                max_tokens=700,
            )
            advocate_args.append(advocate_response)
            transcript += f"ADVOCATE {source_model} (Round {round_num}): {advocate_response}\n\n"

            critic_response = await critic_client.generate(
                system=ANSWER_CRITIC_SYSTEM,
                prompt=(
                    f"{transcript}---\nRound {round_num}/{actual_rounds}. "
                    "Critique whether this answer really answers the meaning of life."
                ),
                max_tokens=700,
            )
            critic_args.append(critic_response)
            transcript += f"CRITIC {critic_model} (Round {round_num}): {critic_response}\n\n"

        judge_response = await self.judge_client.generate(
            system=ANSWER_JUDGE_SYSTEM,
            prompt=f'{transcript}---\nJudge the candidate answer "{answer}". Respond with ONLY valid JSON.',
            max_tokens=400,
            temperature=0.2,
        )
        scores = self._parse_judge_response(judge_response)
        composite = (
            0.30 * scores["directness"]
            + 0.30 * scores["depth"]
            + 0.20 * scores["universality"]
            + 0.20 * scores["resilience"]
        )

        logger.info(
            "[JUDGE] \"%s\" direct=%.0f depth=%.0f universal=%.0f resilient=%.0f composite=%.2f",
            answer[:60],
            scores["directness"],
            scores["depth"],
            scores["universality"],
            scores["resilience"],
            composite,
        )

        return ComparisonResult(
            answer=answer,
            source_model=source_model,
            advocate_model=source_model,
            critic_model=critic_model,
            advocate_arguments=advocate_args,
            critic_arguments=critic_args,
            judge_reasoning=scores.get("reasoning", ""),
            scores={k: v for k, v in scores.items() if k != "reasoning"},
            composite_score=composite,
            rounds=actual_rounds,
            duration_seconds=time.time() - start,
        )

    def _parse_judge_response(self, response: str) -> dict:
        try:
            cleaned = response.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            start = cleaned.index("{")
            end = cleaned.rindex("}") + 1
            data = json.loads(cleaned[start:end])
            return {
                "directness": max(0, min(10, float(data.get("directness", 0)))),
                "depth": max(0, min(10, float(data.get("depth", 0)))),
                "universality": max(0, min(10, float(data.get("universality", 0)))),
                "resilience": max(0, min(10, float(data.get("resilience", 0)))),
                "reasoning": data.get("reasoning", ""),
            }
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning("[JUDGE] Failed to parse comparison judge response: %s", e)
            return {
                "directness": 3.0,
                "depth": 3.0,
                "universality": 3.0,
                "resilience": 3.0,
                "reasoning": f"Parse error, default scores assigned: {e}",
            }
