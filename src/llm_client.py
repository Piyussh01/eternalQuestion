"""
LLM Client for local model inference via vLLM OpenAI-compatible API.

Supports two model instances:
- Explorer (Gemma 4 E4B): Fast perspective/question generation
- Reasoner (Gemma 4 26B MoE): Answer synthesis, debate, and judging
"""

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger("deep-thought.llm")


@dataclass
class ModelConfig:
    name: str
    base_url: str
    model_id: str
    temperature: float = 0.8
    top_p: float = 0.95


# Default configs — override via config/models.json
EXPLORER_CONFIG = ModelConfig(
    name="explorer",
    base_url="http://localhost:8001/v1",
    model_id="google/gemma-4-E4B-it",
    temperature=0.9,   # Higher temp for creative exploration
    top_p=0.95,
)

REASONER_CONFIG = ModelConfig(
    name="reasoner",
    base_url="http://localhost:8002/v1",
    model_id="google/gemma-4-26b-a4b-it",
    temperature=0.6,   # Lower temp for coherent reasoning
    top_p=0.9,
)


class LLMClient:
    """Async client for a single vLLM instance."""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
        self._request_count = 0
        self._total_tokens = 0

    async def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1024,
        temperature: float | None = None,
        stop: list[str] | None = None,
    ) -> str:
        """Generate a completion from the local model."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.config.model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature or self.config.temperature,
            "top_p": self.config.top_p,
        }
        if stop:
            payload["stop"] = stop

        start = time.time()
        try:
            response = await self.client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            elapsed = time.time() - start

            self._request_count += 1
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            self._total_tokens += prompt_tokens + completion_tokens

            tokens_per_sec = completion_tokens / elapsed if elapsed > 0 else 0

            logger.debug(
                "[LLM:%s] %d tokens in %.1fs (%.1f tok/s) | total requests: %d",
                self.config.name, completion_tokens, elapsed,
                tokens_per_sec, self._request_count,
            )

            return content

        except httpx.HTTPStatusError as e:
            logger.error("[LLM:%s] HTTP error: %s", self.config.name, e)
            raise
        except httpx.TimeoutException:
            logger.error("[LLM:%s] Request timed out after 120s", self.config.name)
            raise
        except Exception as e:
            logger.error("[LLM:%s] Unexpected error: %s", self.config.name, e)
            raise

    async def health_check(self) -> bool:
        """Check if the vLLM instance is responsive."""
        try:
            resp = await self.client.get("/models")
            return resp.status_code == 200
        except Exception:
            return False

    def get_stats(self) -> dict:
        return {
            "model": self.config.name,
            "model_id": self.config.model_id,
            "requests": self._request_count,
            "total_tokens": self._total_tokens,
        }

    async def close(self):
        await self.client.aclose()
