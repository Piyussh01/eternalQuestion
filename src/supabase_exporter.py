"""Export public experiment data from local SQLite to Supabase.

This process is intentionally read-only against the experiment database. It
mirrors candidate answers, public debate/evaluation records, and phase events
to Supabase so a hosted dashboard can update while the Spark remains private.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = "logs/deep_thought.db"
DEFAULT_STATE_PATH = "logs/supabase_exporter_state.json"
BATCH_SIZE = 100


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.environ.get("DEEP_THOUGHT_DB_PATH", DEFAULT_DB_PATH))
    parser.add_argument("--state", default=os.environ.get("SUPABASE_EXPORT_STATE", DEFAULT_STATE_PATH))
    parser.add_argument("--interval", type=float, default=float(os.environ.get("SUPABASE_EXPORT_INTERVAL", "5")))
    args = parser.parse_args()

    url = required_env("SUPABASE_URL").rstrip("/")
    service_key = required_env("SUPABASE_SERVICE_ROLE_KEY")
    state_path = Path(args.state)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[supabase-exporter] db={args.db} interval={args.interval}s", flush=True)

    while True:
        try:
            state = load_state(state_path)
            state = export_once(Path(args.db), url, service_key, state)
            write_state(state_path, state)
        except Exception as error:
            print(f"[supabase-exporter] error: {error}", flush=True)
        time.sleep(args.interval)


def export_once(db_path: Path, url: str, key: str, state: dict[str, int]) -> dict[str, int]:
    if not db_path.exists():
        print(f"[supabase-exporter] waiting for {db_path}", flush=True)
        return state

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)
    conn.row_factory = sqlite3.Row
    try:
        candidates = rows_after(
            conn,
            "candidate_answers",
            state.get("candidate_answers", 0),
            """
            SELECT id, answer, source_model, parent_answer, prompt_variant, created_at
            FROM candidate_answers
            WHERE id > ?
            ORDER BY id
            LIMIT ?
            """,
        )
        if candidates:
            upsert(url, key, "public_candidates", [dict(row) for row in candidates])
            state["candidate_answers"] = max(row["id"] for row in candidates)

        evaluations = rows_after(
            conn,
            "candidate_evaluations",
            state.get("candidate_evaluations", 0),
            """
            SELECT id, candidate_id, evaluator_model, opponent_model, rounds,
                   transcript_json, scores_json, composite_score, judge_reasoning,
                   config_json, created_at
            FROM candidate_evaluations
            WHERE id > ?
            ORDER BY id
            LIMIT ?
            """,
        )
        if evaluations:
            upsert(url, key, "public_evaluations", [evaluation_payload(row) for row in evaluations])
            state["candidate_evaluations"] = max(row["id"] for row in evaluations)

        phases = rows_after(
            conn,
            "phase_log",
            state.get("phase_log", 0),
            """
            SELECT id, phase, event, payload_json, created_at
            FROM phase_log
            WHERE id > ?
            ORDER BY id
            LIMIT ?
            """,
        )
        if phases:
            upsert(url, key, "public_phase_log", [phase_payload(row) for row in phases])
            state["phase_log"] = max(row["id"] for row in phases)

        exported = len(candidates) + len(evaluations) + len(phases)
        if exported:
            print(f"[supabase-exporter] exported {exported} rows", flush=True)
        return state
    finally:
        conn.close()


def rows_after(conn: sqlite3.Connection, table: str, last_id: int, sql: str) -> list[sqlite3.Row]:
    try:
        return conn.execute(sql, (last_id, BATCH_SIZE)).fetchall()
    except sqlite3.OperationalError as error:
        if "no such table" in str(error):
            print(f"[supabase-exporter] waiting for table {table}", flush=True)
            return []
        raise


def evaluation_payload(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["transcript_json"] = json_or_empty(data.get("transcript_json"))
    data["scores_json"] = json_or_empty(data.get("scores_json"))
    data["config_json"] = json_or_none(data.get("config_json"))
    return data


def phase_payload(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["payload_json"] = json_or_none(data.get("payload_json"))
    return data


def json_or_empty(value: Any) -> dict[str, Any]:
    parsed = json_or_none(value)
    return parsed if isinstance(parsed, dict) else {}


def json_or_none(value: Any) -> Any:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def upsert(url: str, key: str, table: str, rows: list[dict[str, Any]]) -> None:
    request = urllib.request.Request(
        f"{url}/rest/v1/{table}?on_conflict=id",
        data=json.dumps(rows).encode("utf-8"),
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status not in (200, 201, 204):
                raise RuntimeError(f"Supabase returned HTTP {response.status}")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase {table} upsert failed: HTTP {error.code}: {body}") from error


def load_state(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return {key: int(value) for key, value in raw.items()}


def write_state(path: Path, state: dict[str, int]) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


if __name__ == "__main__":
    main()
