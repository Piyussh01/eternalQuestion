"""
Monte Carlo Tree Search for the Ultimate Question.

Each node in the tree represents a candidate question.
Expansion generates new candidate questions.
Simulation runs a debate round.
Backpropagation updates scores up the tree.
"""

import math
import sqlite3
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

logger = logging.getLogger("deep-thought.mcts")


@dataclass
class MCTSNode:
    id: int
    question: str
    parent_id: Optional[int]
    visits: int = 0
    total_score: float = 0.0
    math_score: float = 0.0
    philosophy_score: float = 0.0
    humor_score: float = 0.0
    universality_score: float = 0.0
    depth: int = 0
    created_at: float = field(default_factory=time.time)
    children_ids: list[int] = field(default_factory=list)

    @property
    def avg_score(self) -> float:
        return self.total_score / self.visits if self.visits > 0 else 0.0


class MCTSTree:
    """Persistent MCTS tree backed by SQLite."""

    def __init__(self, db_path: str = "logs/mcts_tree.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        self._ensure_root()

    def _init_db(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                parent_id INTEGER,
                visits INTEGER DEFAULT 0,
                total_score REAL DEFAULT 0.0,
                math_score REAL DEFAULT 0.0,
                philosophy_score REAL DEFAULT 0.0,
                humor_score REAL DEFAULT 0.0,
                universality_score REAL DEFAULT 0.0,
                depth INTEGER DEFAULT 0,
                created_at REAL,
                FOREIGN KEY (parent_id) REFERENCES nodes(id)
            );

            CREATE TABLE IF NOT EXISTS debates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id INTEGER NOT NULL,
                proposer_argument TEXT,
                opponent_argument TEXT,
                judge_reasoning TEXT,
                math_score REAL,
                philosophy_score REAL,
                humor_score REAL,
                universality_score REAL,
                composite_score REAL,
                created_at REAL,
                FOREIGN KEY (node_id) REFERENCES nodes(id)
            );

            CREATE TABLE IF NOT EXISTS run_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phase TEXT,
                exploration_constant REAL,
                total_nodes INTEGER,
                total_debates INTEGER,
                top_score REAL,
                top_question TEXT,
                timestamp REAL
            );

            CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
            CREATE INDEX IF NOT EXISTS idx_nodes_score ON nodes(total_score);
            CREATE INDEX IF NOT EXISTS idx_debates_node ON debates(node_id);
        """)
        self.conn.commit()

    def _ensure_root(self):
        row = self.conn.execute("SELECT id FROM nodes WHERE parent_id IS NULL").fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO nodes (question, parent_id, depth, created_at) VALUES (?, NULL, 0, ?)",
                ("The Ultimate Question of Life, the Universe, and Everything", time.time()),
            )
            self.conn.commit()
            logger.info("[MCTS] Root node created")

    def get_node(self, node_id: int) -> MCTSNode:
        row = self.conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if row is None:
            raise ValueError(f"Node {node_id} not found")
        children = self.conn.execute(
            "SELECT id FROM nodes WHERE parent_id = ?", (node_id,)
        ).fetchall()
        return MCTSNode(
            id=row["id"],
            question=row["question"],
            parent_id=row["parent_id"],
            visits=row["visits"],
            total_score=row["total_score"],
            math_score=row["math_score"],
            philosophy_score=row["philosophy_score"],
            humor_score=row["humor_score"],
            universality_score=row["universality_score"],
            depth=row["depth"],
            created_at=row["created_at"],
            children_ids=[r["id"] for r in children],
        )

    def get_root(self) -> MCTSNode:
        row = self.conn.execute("SELECT id FROM nodes WHERE parent_id IS NULL").fetchone()
        return self.get_node(row["id"])

    def select(self, exploration_constant: float = 1.414) -> MCTSNode:
        """UCB1-based selection from root to leaf."""
        node = self.get_root()
        path = [node]

        while node.children_ids:
            best_child = None
            best_ucb = -float("inf")
            parent_visits = max(node.visits, 1)

            for child_id in node.children_ids:
                child = self.get_node(child_id)
                if child.visits == 0:
                    # Unvisited nodes get infinite priority
                    return child

                exploitation = child.avg_score / 10.0  # Normalize to [0, 1]
                exploration = exploration_constant * math.sqrt(
                    math.log(parent_visits) / child.visits
                )
                ucb = exploitation + exploration

                if ucb > best_ucb:
                    best_ucb = ucb
                    best_child = child

            if best_child is None:
                break
            node = best_child
            path.append(node)

        logger.info(
            "[MCTS] Selected node %d (depth=%d, visits=%d, avg=%.2f): %s",
            node.id, node.depth, node.visits, node.avg_score,
            node.question[:80],
        )
        return node

    def expand(self, parent_id: int, questions: list[str]) -> list[MCTSNode]:
        """Add child nodes with new candidate questions."""
        parent = self.get_node(parent_id)
        new_nodes = []

        for q in questions:
            cursor = self.conn.execute(
                "INSERT INTO nodes (question, parent_id, depth, created_at) VALUES (?, ?, ?, ?)",
                (q, parent_id, parent.depth + 1, time.time()),
            )
            new_node = self.get_node(cursor.lastrowid)
            new_nodes.append(new_node)
            logger.info("[MCTS] Expanded node %d -> %d: %s", parent_id, new_node.id, q[:80])

        self.conn.commit()
        return new_nodes

    def backpropagate(self, node_id: int, scores: dict[str, float]):
        """Update node and all ancestors with debate scores."""
        composite = (
            0.25 * scores["math"]
            + 0.30 * scores["philosophy"]
            + 0.25 * scores["humor"]
            + 0.20 * scores["universality"]
        )

        current_id = node_id
        while current_id is not None:
            self.conn.execute(
                """UPDATE nodes SET
                    visits = visits + 1,
                    total_score = total_score + ?,
                    math_score = CASE WHEN ? > math_score THEN ? ELSE math_score END,
                    philosophy_score = CASE WHEN ? > philosophy_score THEN ? ELSE philosophy_score END,
                    humor_score = CASE WHEN ? > humor_score THEN ? ELSE humor_score END,
                    universality_score = CASE WHEN ? > universality_score THEN ? ELSE universality_score END
                WHERE id = ?""",
                (
                    composite,
                    scores["math"], scores["math"],
                    scores["philosophy"], scores["philosophy"],
                    scores["humor"], scores["humor"],
                    scores["universality"], scores["universality"],
                    current_id,
                ),
            )
            row = self.conn.execute(
                "SELECT parent_id FROM nodes WHERE id = ?", (current_id,)
            ).fetchone()
            current_id = row["parent_id"] if row else None

        self.conn.commit()
        logger.info(
            "[MCTS] Backpropagated node %d: composite=%.2f (math=%.1f phil=%.1f humor=%.1f univ=%.1f)",
            node_id, composite, scores["math"], scores["philosophy"],
            scores["humor"], scores["universality"],
        )

    def record_debate(self, node_id: int, debate_record: dict):
        """Store full debate transcript."""
        self.conn.execute(
            """INSERT INTO debates
                (node_id, proposer_argument, opponent_argument, judge_reasoning,
                 math_score, philosophy_score, humor_score, universality_score,
                 composite_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                node_id,
                debate_record.get("proposer", ""),
                debate_record.get("opponent", ""),
                debate_record.get("judge_reasoning", ""),
                debate_record.get("math", 0),
                debate_record.get("philosophy", 0),
                debate_record.get("humor", 0),
                debate_record.get("universality", 0),
                debate_record.get("composite", 0),
                time.time(),
            ),
        )
        self.conn.commit()

    def record_stats(self, phase: str, exploration_constant: float):
        """Snapshot current run statistics."""
        stats = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM nodes"
        ).fetchone()
        debate_count = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM debates"
        ).fetchone()
        top = self.conn.execute(
            "SELECT question, total_score/CASE WHEN visits>0 THEN visits ELSE 1 END as avg "
            "FROM nodes WHERE visits > 0 ORDER BY avg DESC LIMIT 1"
        ).fetchone()

        self.conn.execute(
            "INSERT INTO run_stats (phase, exploration_constant, total_nodes, total_debates, top_score, top_question, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                phase,
                exploration_constant,
                stats["cnt"],
                debate_count["cnt"],
                top["avg"] if top else 0,
                top["question"] if top else "",
                time.time(),
            ),
        )
        self.conn.commit()

    def get_leaderboard(self, top_n: int = 50) -> list[dict]:
        """Get top-scoring questions."""
        rows = self.conn.execute(
            """SELECT id, question, visits,
                      total_score / CASE WHEN visits > 0 THEN visits ELSE 1 END as avg_score,
                      math_score, philosophy_score, humor_score, universality_score, depth
               FROM nodes
               WHERE visits > 0 AND parent_id IS NOT NULL
               ORDER BY avg_score DESC
               LIMIT ?""",
            (top_n,),
        ).fetchall()

        return [
            {
                "rank": i + 1,
                "id": r["id"],
                "question": r["question"],
                "avg_score": round(r["avg_score"], 3),
                "visits": r["visits"],
                "math": r["math_score"],
                "philosophy": r["philosophy_score"],
                "humor": r["humor_score"],
                "universality": r["universality_score"],
                "depth": r["depth"],
            }
            for i, r in enumerate(rows)
        ]

    def get_tree_stats(self) -> dict:
        """Get aggregate tree statistics."""
        total = self.conn.execute("SELECT COUNT(*) as c FROM nodes").fetchone()["c"]
        visited = self.conn.execute(
            "SELECT COUNT(*) as c FROM nodes WHERE visits > 0"
        ).fetchone()["c"]
        max_depth = self.conn.execute(
            "SELECT MAX(depth) as d FROM nodes"
        ).fetchone()["d"] or 0
        debates = self.conn.execute("SELECT COUNT(*) as c FROM debates").fetchone()["c"]

        return {
            "total_nodes": total,
            "visited_nodes": visited,
            "max_depth": max_depth,
            "total_debates": debates,
        }

    def prune_below(self, threshold: float):
        """Mark low-scoring branches for exclusion (soft prune)."""
        pruned = self.conn.execute(
            """SELECT id, question,
                      total_score / CASE WHEN visits > 0 THEN visits ELSE 1 END as avg
               FROM nodes
               WHERE visits >= 3 AND parent_id IS NOT NULL
               AND (total_score / CASE WHEN visits > 0 THEN visits ELSE 1 END) < ?""",
            (threshold,),
        ).fetchall()

        # We don't delete — we just log. The UCB1 formula naturally deprioritizes them.
        for r in pruned:
            logger.info("[MCTS] Low-scoring node %d (avg=%.2f): %s", r["id"], r["avg"], r["question"][:60])

        return len(pruned)

    def close(self):
        self.conn.close()
