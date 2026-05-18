"""
Question Expander — generates new candidate questions from MCTS nodes.

Uses the fast Gemma 4 26B MoE model for high-throughput generation.
"""

import json
import logging
import re

from src.llm_client import LLMClient

logger = logging.getLogger("deep-thought.expander")

EXPANSION_SYSTEM = """You are a creative philosopher and question generator working on the greatest
puzzle in the universe: finding the Ultimate Question of Life, the Universe, and Everything,
whose answer is 42.

When given a parent question or theme, generate new candidate questions that:
1. Could plausibly have 42 as their answer (literally, mathematically, metaphorically)
2. Address the meaning of life, the universe, and everything
3. Have the right blend of profundity and absurdity (Douglas Adams style)
4. Are genuinely different from the parent — explore NEW angles

You MUST respond with ONLY a JSON array of strings. No other text.
Example: ["What is X?", "How many Y?", "Why Z?"]

Generate exactly {count} questions. Each should be a complete, well-formed question."""

SEED_QUESTIONS = [
    "How many roads must a man walk down?",
    "What is six multiplied by nine?",
    "What is the sum of all human knowledge minus everything we think we know?",
    "How many moments of genuine connection does a conscious being need to understand existence?",
    "What is the number of dimensions in which love makes mathematical sense?",
    "How many questions must be asked before the right one is found?",
    "What is the minimum number of perspectives needed to see the whole universe?",
    "How many times must the universe restart before it gets it right?",
    "What is the atomic number of the element that makes stars conscious?",
    "How many civilizations have asked this exact question before us?",
]


class QuestionExpander:
    """Generates new candidate questions from existing nodes."""

    def __init__(self, explorer_client: LLMClient):
        self.client = explorer_client
        self._expansion_count = 0

    async def expand(self, parent_question: str, count: int = 5, context: str = "") -> list[str]:
        """Generate child candidate questions from a parent."""
        prompt = f"PARENT QUESTION/THEME: \"{parent_question}\"\n\n"
        if context:
            prompt += f"CONTEXT (high-scoring patterns so far):\n{context}\n\n"
        prompt += f"Generate exactly {count} new candidate Ultimate Questions. Each must be distinct and explore a different angle. Respond with ONLY a JSON array."

        system = EXPANSION_SYSTEM.replace("{count}", str(count))

        response = await self.client.generate(
            system=system,
            prompt=prompt,
            max_tokens=1024,
            temperature=0.9,  # High creativity for exploration
        )

        questions = self._parse_questions(response, count)
        self._expansion_count += len(questions)

        logger.info(
            "[EXPAND] Generated %d questions from parent: %s",
            len(questions), parent_question[:60],
        )
        for i, q in enumerate(questions):
            logger.info("[EXPAND]   %d. %s", i + 1, q[:100])

        return questions

    def _parse_questions(self, response: str, expected_count: int) -> list[str]:
        """Parse JSON array of questions from model response."""
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
            questions = json.loads(cleaned[start:end])

            # Validate: must be list of strings
            questions = [str(q).strip() for q in questions if isinstance(q, str) and len(q.strip()) > 10]

            return questions[:expected_count]

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("[EXPAND] JSON parse failed, falling back to line extraction: %s", e)
            # Fallback: extract questions by pattern matching
            lines = response.strip().split("\n")
            questions = []
            for line in lines:
                line = line.strip().strip("-").strip("*").strip()
                # Remove numbering like "1." or "1)"
                line = re.sub(r"^\d+[\.\)]\s*", "", line).strip()
                # Remove surrounding quotes
                line = line.strip('"').strip("'")
                if line and "?" in line and len(line) > 10:
                    questions.append(line)

            return questions[:expected_count]

    def get_seed_questions(self) -> list[str]:
        """Return seed questions for initial tree population."""
        return SEED_QUESTIONS.copy()

    def get_stats(self) -> dict:
        return {"total_expansions": self._expansion_count}
