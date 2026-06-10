#!/usr/bin/env python3
"""
Run the research phase end-to-end.

Examples:
  # Research one lens (cheapest sanity check — 8 Tavily queries)
  python scripts/run_research.py --lens "Theravada Buddhist Monk"

  # Research all 20 lenses (~160 Tavily queries)
  python scripts/run_research.py

Reads TAVILY_API_KEY from the environment. If you have a .env file in the
project root, it is loaded automatically (no python-dotenv dependency needed —
we parse it ourselves).
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Deep Thought 2.0 — research phase")
    parser.add_argument("--lens", help="Limit to a single lens (by name)")
    parser.add_argument("--db", default="logs/deep_thought.db", help="SQLite path")
    args = parser.parse_args()

    _load_env_file(ROOT / ".env")
    _setup_logging()

    from src.db import DB
    from src.research import TavilyClient, research_all_lenses

    db = DB(args.db)
    tavily = TavilyClient.from_env()

    try:
        totals = await research_all_lenses(db, tavily, only=args.lens)
        print()
        print("=" * 60)
        print(f"  lenses processed : {totals['lenses']}")
        print(f"  new queries      : {totals['queried']}")
        print(f"  cache hits       : {totals['cached']}")
        print(f"  failures         : {totals['failed']}")
        print(f"  tavily calls     : {tavily.query_count}")
        print("=" * 60)
        return 0
    finally:
        await tavily.close()
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
