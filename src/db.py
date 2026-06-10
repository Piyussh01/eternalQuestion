"""
SQLite-backed store for the meaning-of-life pipeline.

Holds candidate answers, model comparisons, research artifacts, claims,
debates, and synthesis rounds. Single DB file, opened per-process.
"""

import sqlite3
import time
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("deep-thought.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS lenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    archetype TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS lens_research (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lens_id INTEGER NOT NULL,
    angle TEXT NOT NULL,
    query TEXT NOT NULL,
    results_json TEXT NOT NULL,
    summary TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (lens_id) REFERENCES lenses(id),
    UNIQUE (lens_id, query)
);

CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lens_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    citations_json TEXT NOT NULL,
    round INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    FOREIGN KEY (lens_id) REFERENCES lenses(id)
);

CREATE TABLE IF NOT EXISTS contrast_pairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lens_a_id INTEGER NOT NULL,
    lens_b_id INTEGER NOT NULL,
    contrast_score REAL NOT NULL,
    source TEXT NOT NULL,
    debated INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    FOREIGN KEY (lens_a_id) REFERENCES lenses(id),
    FOREIGN KEY (lens_b_id) REFERENCES lenses(id),
    UNIQUE (lens_a_id, lens_b_id)
);

CREATE TABLE IF NOT EXISTS debates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_a_id INTEGER NOT NULL,
    claim_b_id INTEGER NOT NULL,
    rounds INTEGER NOT NULL,
    transcript_json TEXT NOT NULL,
    opponent_searches_json TEXT NOT NULL,
    judge_reasoning TEXT,
    fault_line TEXT,
    scores_json TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (claim_a_id) REFERENCES claims(id),
    FOREIGN KEY (claim_b_id) REFERENCES claims(id)
);

CREATE TABLE IF NOT EXISTS syntheses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round INTEGER NOT NULL,
    input_claim_ids_json TEXT NOT NULL,
    text TEXT NOT NULL,
    citations_json TEXT NOT NULL,
    score REAL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS final_answer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    citations_json TEXT NOT NULL,
    attacks_survived INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    answer TEXT NOT NULL UNIQUE,
    source_model TEXT NOT NULL,
    parent_answer TEXT,
    prompt_variant TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    evaluator_model TEXT NOT NULL,
    opponent_model TEXT NOT NULL,
    rounds INTEGER NOT NULL,
    transcript_json TEXT NOT NULL,
    scores_json TEXT NOT NULL,
    composite_score REAL NOT NULL,
    judge_reasoning TEXT,
    config_json TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (candidate_id) REFERENCES candidate_answers(id)
);

CREATE TABLE IF NOT EXISTS phase_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase TEXT NOT NULL,
    event TEXT NOT NULL,
    payload_json TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_research_lens ON lens_research(lens_id);
CREATE INDEX IF NOT EXISTS idx_claims_lens ON claims(lens_id);
CREATE INDEX IF NOT EXISTS idx_debates_pair ON debates(claim_a_id, claim_b_id);
CREATE INDEX IF NOT EXISTS idx_contrast_score ON contrast_pairs(contrast_score DESC);
CREATE INDEX IF NOT EXISTS idx_candidate_source ON candidate_answers(source_model);
CREATE INDEX IF NOT EXISTS idx_candidate_score ON candidate_evaluations(composite_score DESC);
"""


class DB:
    def __init__(self, db_path: str = "logs/deep_thought.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        logger.info("[DB] Opened %s", self.db_path)

    # ----- lenses -----

    def upsert_lens(self, name: str, archetype: str, description: str) -> int:
        row = self.conn.execute(
            "SELECT id FROM lenses WHERE name = ?", (name,)
        ).fetchone()
        if row:
            self.conn.execute(
                "UPDATE lenses SET archetype = ?, description = ? WHERE id = ?",
                (archetype, description, row["id"]),
            )
            self.conn.commit()
            return row["id"]
        cur = self.conn.execute(
            "INSERT INTO lenses (name, archetype, description, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (name, archetype, description, time.time()),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_lenses(self, status: Optional[str] = None) -> list[sqlite3.Row]:
        if status:
            return self.conn.execute(
                "SELECT * FROM lenses WHERE status = ? ORDER BY id", (status,)
            ).fetchall()
        return self.conn.execute("SELECT * FROM lenses ORDER BY id").fetchall()

    def get_lens(self, lens_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM lenses WHERE id = ?", (lens_id,)
        ).fetchone()

    def get_lens_by_name(self, name: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM lenses WHERE name = ?", (name,)
        ).fetchone()

    def set_lens_status(self, lens_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE lenses SET status = ? WHERE id = ?", (status, lens_id)
        )
        self.conn.commit()

    # ----- research -----

    def has_research(self, lens_id: int, query: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM lens_research WHERE lens_id = ? AND query = ?",
            (lens_id, query),
        ).fetchone()
        return row is not None

    def save_research(
        self,
        lens_id: int,
        angle: str,
        query: str,
        results: dict,
        summary: Optional[str] = None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO lens_research "
            "(lens_id, angle, query, results_json, summary, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (lens_id, angle, query, json.dumps(results), summary, time.time()),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_research(self, lens_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM lens_research WHERE lens_id = ? ORDER BY id",
            (lens_id,),
        ).fetchall()

    # ----- phase log (general event stream for the Next.js UI) -----

    # ----- candidate search -----

    def save_candidate(
        self,
        answer: str,
        source_model: str,
        parent_answer: Optional[str] = None,
        prompt_variant: Optional[str] = None,
    ) -> int:
        row = self.conn.execute(
            "SELECT id FROM candidate_answers WHERE answer = ?", (answer,)
        ).fetchone()
        if row:
            return row["id"]
        cur = self.conn.execute(
            "INSERT INTO candidate_answers "
            "(answer, source_model, parent_answer, prompt_variant, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (answer, source_model, parent_answer, prompt_variant, time.time()),
        )
        self.conn.commit()
        return cur.lastrowid

    def save_candidate_evaluation(
        self,
        candidate_id: int,
        evaluator_model: str,
        opponent_model: str,
        rounds: int,
        transcript: dict,
        scores: dict,
        composite_score: float,
        judge_reasoning: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO candidate_evaluations "
            "(candidate_id, evaluator_model, opponent_model, rounds, transcript_json, "
            "scores_json, composite_score, judge_reasoning, config_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                candidate_id,
                evaluator_model,
                opponent_model,
                rounds,
                json.dumps(transcript),
                json.dumps(scores),
                composite_score,
                judge_reasoning,
                json.dumps(config) if config else None,
                time.time(),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_candidate_leaderboard(self, top_n: int = 10) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT
                q.id,
                q.answer,
                q.source_model,
                COUNT(e.id) AS evaluations,
                AVG(e.composite_score) AS avg_score,
                MAX(e.composite_score) AS best_score
            FROM candidate_answers q
            JOIN candidate_evaluations e ON e.candidate_id = q.id
            GROUP BY q.id
            ORDER BY avg_score DESC, best_score DESC
            LIMIT ?
            """,
            (top_n,),
        ).fetchall()
        return [
            {
                "rank": i + 1,
                "id": row["id"],
                "answer": row["answer"],
                "source_model": row["source_model"],
                "evaluations": row["evaluations"],
                "avg_score": row["avg_score"],
                "best_score": row["best_score"],
            }
            for i, row in enumerate(rows)
        ]

    def get_candidate_stats(self) -> dict:
        row = self.conn.execute(
            """
            SELECT
                COUNT(DISTINCT q.id) AS candidates,
                COUNT(e.id) AS evaluations,
                COALESCE(AVG(e.composite_score), 0) AS avg_score
            FROM candidate_answers q
            LEFT JOIN candidate_evaluations e ON e.candidate_id = q.id
            """
        ).fetchone()
        by_model = self.conn.execute(
            """
            SELECT source_model, COUNT(*) AS candidates
            FROM candidate_answers
            GROUP BY source_model
            ORDER BY source_model
            """
        ).fetchall()
        return {
            "candidates": row["candidates"],
            "evaluations": row["evaluations"],
            "avg_score": row["avg_score"],
            "by_model": {r["source_model"]: r["candidates"] for r in by_model},
        }

    def log_event(self, phase: str, event: str, payload: Optional[dict] = None) -> None:
        self.conn.execute(
            "INSERT INTO phase_log (phase, event, payload_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (phase, event, json.dumps(payload) if payload else None, time.time()),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
