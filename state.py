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


def init_db() -> None:
    """
    Create the bot_state table if it doesn't exist.
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
            return True, False  # found, just marked complete
    return False, False  # not in this cycle


def all_complete(state: dict) -> bool:
    """Return True if every assignment in the current cycle is completed."""
    assignments = state.get("assignments", [])
    return bool(assignments) and all(a["completed"] for a in assignments)


def incomplete_assignments(state: dict) -> list[dict]:
    """Return a list of assignment dicts that are not yet completed."""
    return [a for a in state.get("assignments", []) if not a["completed"]]
