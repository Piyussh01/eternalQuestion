"""
Perspective and answer generation for the meaning-of-life experiment.
"""

import json
import logging
import re

from src.llm_client import LLMClient

logger = logging.getLogger("deep-thought.expander")

PERSPECTIVE_SYSTEM = """You are generating perspective probes for one fixed question:
"What is the meaning of life?"

Generate questions that help a stronger reasoning model understand the target
from many human and non-human angles. These are not final answers and not a
search for a different "ultimate question." They are lenses for testing what a
good final answer must survive.

Cover distinct perspectives such as:
- birth, death, love, grief, work, play, suffering, duty, freedom
- science, religion, philosophy, art, ecology, family, civilization
- child, elder, parent, outsider, skeptic, mystic, builder, patient

You MUST respond with ONLY a JSON array of strings. No other text.
Example: ["What would this answer mean to someone facing death?", "Would this answer still work for a child?"]

Generate exactly {count} perspective questions."""

ANSWER_SYSTEM = """You are generating candidate answers to one fixed question:
"What is the meaning of life?"

Generate answers that:
1. Directly answer the meaning of life, nothing more and nothing less
2. Are concise enough to survive scrutiny, but not shallow
3. Respond to the supplied perspective without becoming narrow
4. Are genuinely different from previous candidates

You MUST respond with ONLY a JSON array of strings. No other text.
Example: ["To...", "Meaning is...", "Life means..."]

Generate exactly {count} answers. Each should be a complete answer."""

SEED_ANSWERS = [
    "The meaning of life is to reduce suffering and increase understanding.",
    "The meaning of life is to create meaning where none is guaranteed.",
    "The meaning of life is conscious participation in reality.",
    "The meaning of life is to love, learn, and leave the world less confused.",
    "The meaning of life is the answer a finite being gives to infinity.",
]


class AnswerGenerator:
    """Generates perspective probes and candidate answers."""

    def __init__(self, explorer_client: LLMClient):
        self.client = explorer_client
        self._expansion_count = 0

    async def generate_perspectives(
        self,
        seed: str,
        count: int = 5,
        context: str = "",
        prompt_suffix: str = "",
        temperature: float | None = None,
    ) -> list[str]:
        """Generate questions/lenses for exploring the target answer."""
        prompt = f"TARGET QUESTION: \"What is the meaning of life?\"\n\nSEED/THEME: \"{seed}\"\n\n"
        if context:
            prompt += f"CURRENT HIGH-SCORING ANSWERS:\n{context}\n\n"
        if prompt_suffix:
            prompt += f"EXPERIMENTAL GUIDANCE:\n{prompt_suffix}\n\n"
        prompt += (
            f"Generate exactly {count} perspective questions that reveal different "
            "requirements a final answer must satisfy. Respond with ONLY a JSON array."
        )

        system = PERSPECTIVE_SYSTEM.replace("{count}", str(count))

        response = await self.client.generate(
            system=system,
            prompt=prompt,
            max_tokens=900,
            temperature=temperature if temperature is not None else 0.9,
        )

        questions = self._parse_items(response, count)
        self._expansion_count += len(questions)

        logger.info("[EXPAND] Generated %d perspective questions from theme: %s", len(questions), seed[:60])
        for i, question in enumerate(questions):
            logger.info("[EXPAND]   Q%d. %s", i + 1, question[:120])

        return questions

    async def generate_answers(
        self,
        perspective_question: str,
        count: int = 5,
        context: str = "",
        prompt_suffix: str = "",
        temperature: float | None = None,
    ) -> list[str]:
        """Generate candidate answers from a perspective probe."""
        prompt = (
            f"TARGET QUESTION: \"What is the meaning of life?\"\n\n"
            f"PERSPECTIVE QUESTION: \"{perspective_question}\"\n\n"
        )
        if context:
            prompt += f"CONTEXT (high-scoring answers so far):\n{context}\n\n"
        if prompt_suffix:
            prompt += f"EXPERIMENTAL GUIDANCE:\n{prompt_suffix}\n\n"
        prompt += (
            f"Generate exactly {count} candidate answers. Each answer must directly answer "
            "the target question while passing through the perspective question. "
            "Respond with ONLY a JSON array."
        )

        system = ANSWER_SYSTEM.replace("{count}", str(count))

        response = await self.client.generate(
            system=system,
            prompt=prompt,
            max_tokens=1024,
            temperature=temperature if temperature is not None else 0.9,
        )

        answers = self._parse_items(response, count)
        self._expansion_count += len(answers)

        logger.info(
            "[EXPAND] Generated %d answers from perspective: %s",
            len(answers), perspective_question[:60],
        )
        for i, answer in enumerate(answers):
            logger.info("[EXPAND]   %d. %s", i + 1, answer[:100])

        return answers

    async def generate(
        self,
        seed: str,
        count: int = 5,
        context: str = "",
        prompt_suffix: str = "",
        temperature: float | None = None,
    ) -> list[str]:
        """Backward-compatible answer generation entry point."""
        return await self.generate_answers(seed, count, context, prompt_suffix, temperature)

    def _parse_items(self, response: str, expected_count: int) -> list[str]:
        """Parse a JSON array of strings from model response."""
        try:
            # Try direct JSON parse
            cleaned = response.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()

            # Find the array
            start = cleaned.index("[")
            end = cleaned.rindex("]") + 1
            items = json.loads(cleaned[start:end])

            # Validate: must be list of strings
            items = [str(q).strip() for q in items if isinstance(q, str) and len(q.strip()) > 10]

            return items[:expected_count]

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("[EXPAND] JSON parse failed, falling back to line extraction: %s", e)
            # Fallback: extract answers by line.
            lines = response.strip().split("\n")
            items = []
            for line in lines:
                line = line.strip().strip("-").strip("*").strip()
                # Remove numbering like "1." or "1)"
                line = re.sub(r"^\d+[\.\)]\s*", "", line).strip()
                # Remove surrounding quotes
                line = line.strip('"').strip("'")
                if line and len(line) > 10:
                    items.append(line)

            return items[:expected_count]

    def get_seed_answers(self) -> list[str]:
        """Return seed answers."""
        return SEED_ANSWERS.copy()

    def get_stats(self) -> dict:
        return {"total_expansions": self._expansion_count}
