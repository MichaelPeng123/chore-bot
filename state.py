"""
state.py — Read/write helpers for persistent state.
State is stored in a PostgreSQL database (DATABASE_URL env var) so it survives
bot restarts and ephemeral deployments (e.g. Railway).
"""

import json
import logging
import os
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


def _get_conn():
    """Open and return a new database connection."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("[state] DATABASE_URL environment variable is not set.")
    return psycopg2.connect(database_url)


def init_db(roommates: list[dict]) -> None:
    """
    Create the bot_state, assignment_history, and leaderboard tables if they don't exist.
    Seeds the leaderboard with each roommate (no-op if they already exist).
    Call once at startup before any load/save operations.
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_state (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    data JSONB NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS assignment_history (
                    cycle_number INTEGER PRIMARY KEY,
                    cycle_start  TIMESTAMPTZ,
                    cycle_end    TIMESTAMPTZ,
                    assignments  JSONB NOT NULL,
                    archived_at  TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS leaderboard (
                    discord_user_id TEXT PRIMARY KEY,
                    name            TEXT NOT NULL,
                    points          INTEGER NOT NULL DEFAULT 0
                )
            """)
            for r in roommates:
                cur.execute("""
                    INSERT INTO leaderboard (discord_user_id, name)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, (r["discord_user_id"], r["name"]))
        conn.commit()
    logger.info("[state] Database initialised.")


def load_state() -> dict:
    """
    Read state from the database and return the parsed dict.
    Returns {} if no row exists yet.
    """
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT data FROM bot_state WHERE id = 1")
                row = cur.fetchone()
                if row is None:
                    return {}
                return dict(row["data"])
    except Exception as e:
        logger.warning(f"[state] Failed to load state ({e}). Returning empty state.")
        return {}


def save_state(state: dict) -> None:
    """Upsert the given dict into the database."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO bot_state (id, data) VALUES (1, %s)
                    ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data
                """, (json.dumps(state, default=str),))
            conn.commit()
    except Exception as e:
        logger.error(f"[state] Failed to save state: {e}")


def is_active_cycle(state: dict) -> bool:
    """Return True if state contains a cycle that has not yet ended."""
    if not state or "cycle_end" not in state:
        return False
    try:
        cycle_end = datetime.fromisoformat(state["cycle_end"])
        # Make cycle_end timezone-aware (UTC) if it's naive
        if cycle_end.tzinfo is None:
            cycle_end = cycle_end.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < cycle_end
    except (ValueError, TypeError):
        return False


def add_points(discord_user_id: str, points: int) -> None:
    """Add points to a user's leaderboard total."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE leaderboard SET points = points + %s WHERE discord_user_id = %s",
                    (points, discord_user_id),
                )
            conn.commit()
    except Exception as e:
        logger.error(f"[state] Failed to add points: {e}")


def load_leaderboard() -> list[dict]:
    """Return all leaderboard entries ordered by points descending."""
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT discord_user_id, name, points FROM leaderboard ORDER BY points DESC")
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"[state] Failed to load leaderboard: {e}")
        return []


def mark_assignment_complete(state: dict, discord_user_id: str) -> tuple[bool, bool]:
    """
    Find the assignment for the given user and mark it complete.

    Returns:
        (found, already_complete) — both False if user not in assignments.
    """
    for assignment in state.get("assignments", []):
        if assignment["discord_user_id"] == discord_user_id:
            if assignment["completed"]:
                return True, True  # found, already done
            assignment["completed"] = True
            assignment["completed_at"] = datetime.now(timezone.utc).isoformat()
            save_state(state)
            add_points(discord_user_id, 2)
            return True, False  # found, just marked complete
    return False, False  # not in this cycle


def all_complete(state: dict) -> bool:
    """Return True if every assignment in the current cycle is completed."""
    assignments = state.get("assignments", [])
    return bool(assignments) and all(a["completed"] for a in assignments)


def incomplete_assignments(state: dict) -> list[dict]:
    """Return a list of assignment dicts that are not yet completed."""
    return [a for a in state.get("assignments", []) if not a["completed"]]


def archive_cycle(state: dict) -> None:
    """
    Save the given cycle to assignment_history.
    Safe to call multiple times — ON CONFLICT DO NOTHING prevents duplicates.
    """
    if not state or "cycle_number" not in state:
        return
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO assignment_history
                        (cycle_number, cycle_start, cycle_end, assignments)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (cycle_number) DO NOTHING
                """, (
                    state["cycle_number"],
                    state.get("cycle_start"),
                    state.get("cycle_end"),
                    json.dumps(state.get("assignments", []), default=str),
                ))
            conn.commit()
        logger.info(f"[state] Archived cycle {state['cycle_number']}.")
    except Exception as e:
        logger.error(f"[state] Failed to archive cycle: {e}")


def load_history(limit: int = 5) -> list[dict]:
    """
    Return the last `limit` completed cycles, most recent first.
    Each entry has: cycle_number, cycle_start, cycle_end, assignments.
    """
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT cycle_number, cycle_start, cycle_end, assignments
                    FROM assignment_history
                    ORDER BY cycle_number DESC
                    LIMIT %s
                """, (limit,))
                rows = cur.fetchall()
                return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[state] Failed to load history: {e}")
        return []
