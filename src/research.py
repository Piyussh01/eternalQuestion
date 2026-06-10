"""
Web research via Tavily — populates `lens_research` with grounded source material
that later phases (steelman, debate, synthesis) draw from.

Caching: SQLite UNIQUE(lens_id, query) means re-running this is a no-op for any
query already answered. Useful when iterating on later phases without burning
the Tavily quota.

Budget: 20 lenses × 8 angles = 160 queries for the full research phase.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx

from src.db import DB
from src.lenses import Lens, angles_for, get_seed_lenses

logger = logging.getLogger("deep-thought.research")

TAVILY_URL = "https://api.tavily.com/search"


@dataclass
class TavilyConfig:
    api_key: str
    search_depth: str = "advanced"
    max_results: int = 5
    include_answer: bool = True
    timeout_s: float = 30.0


class TavilyClient:
    """Tiny async wrapper around Tavily's /search endpoint."""

    def __init__(self, config: TavilyConfig):
        self.config = config
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(config.timeout_s, connect=10.0))
        self._query_count = 0

    @classmethod
    def from_env(cls) -> "TavilyClient":
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            raise RuntimeError(
                "TAVILY_API_KEY is not set. Add it to your environment or .env file."
            )
        return cls(TavilyConfig(api_key=api_key))

    async def search(self, query: str) -> dict:
        payload = {
            "api_key": self.config.api_key,
            "query": query,
            "search_depth": self.config.search_depth,
            "max_results": self.config.max_results,
            "include_answer": self.config.include_answer,
        }
        resp = await self.client.post(TAVILY_URL, json=payload)
        resp.raise_for_status()
        self._query_count += 1
        return resp.json()

    @property
    def query_count(self) -> int:
        return self._query_count

    async def close(self) -> None:
        await self.client.aclose()


def _summarize_results(results: dict) -> Optional[str]:
    """Extract Tavily's own answer if present; else stitch top snippets."""
    answer = results.get("answer")
    if answer:
        return answer.strip()
    items = results.get("results") or []
    if not items:
        return None
    snippets = []
    for item in items[:3]:
        title = item.get("title", "")
        content = (item.get("content") or "").strip()
        if content:
            snippets.append(f"{title}: {content}")
    return "\n\n".join(snippets) if snippets else None


async def research_lens(
    db: DB,
    tavily: TavilyClient,
    lens: Lens,
    *,
    sleep_between_s: float = 0.3,
) -> dict:
    """Run all research angles for one lens. Returns per-angle counts."""
    lens_row = db.get_lens_by_name(lens.name)
    if lens_row is None:
        lens_id = db.upsert_lens(lens.name, lens.archetype, lens.description)
    else:
        lens_id = lens_row["id"]

    db.set_lens_status(lens_id, "researching")
    db.log_event("research", "lens_start", {"lens_id": lens_id, "name": lens.name})

    stats = {"queried": 0, "cached": 0, "failed": 0}
    for angle, query in angles_for(lens):
        if db.has_research(lens_id, query):
            stats["cached"] += 1
            logger.info("[RESEARCH] cache hit lens=%s angle=%s", lens.name, angle)
            continue
        try:
            results = await tavily.search(query)
        except httpx.HTTPError as e:
            logger.error("[RESEARCH] tavily error lens=%s angle=%s: %s", lens.name, angle, e)
            stats["failed"] += 1
            db.log_event("research", "query_failed", {
                "lens_id": lens_id, "angle": angle, "query": query, "error": str(e),
            })
            continue

        summary = _summarize_results(results)
        db.save_research(lens_id, angle, query, results, summary)
        stats["queried"] += 1
        logger.info(
            "[RESEARCH] lens=%s angle=%s results=%d summary=%s",
            lens.name, angle, len(results.get("results") or []),
            (summary or "")[:80].replace("\n", " "),
        )
        await asyncio.sleep(sleep_between_s)

    db.set_lens_status(lens_id, "researched")
    db.log_event("research", "lens_done", {"lens_id": lens_id, "name": lens.name, **stats})
    logger.info(
        "[RESEARCH] DONE lens=%s queried=%d cached=%d failed=%d",
        lens.name, stats["queried"], stats["cached"], stats["failed"],
    )
    return stats


async def research_all_lenses(
    db: DB,
    tavily: TavilyClient,
    only: Optional[str] = None,
) -> dict:
    """Run research for every seed lens (or just one if `only` given)."""
    lenses = get_seed_lenses()
    if only:
        lenses = [l for l in lenses if l.name.lower() == only.lower()]
        if not lenses:
            raise ValueError(f"Lens not found: {only}")

    # Make sure all lenses exist in the DB even if we're only researching one
    for l in get_seed_lenses():
        db.upsert_lens(l.name, l.archetype, l.description)

    totals = {"queried": 0, "cached": 0, "failed": 0, "lenses": 0}
    for lens in lenses:
        stats = await research_lens(db, tavily, lens)
        totals["queried"] += stats["queried"]
        totals["cached"] += stats["cached"]
        totals["failed"] += stats["failed"]
        totals["lenses"] += 1

    logger.info(
        "[RESEARCH] ALL DONE lenses=%d queried=%d cached=%d failed=%d tavily_count=%d",
        totals["lenses"], totals["queried"], totals["cached"], totals["failed"],
        tavily.query_count,
    )
    return totals
