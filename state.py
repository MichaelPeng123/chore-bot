"""
state.py — Read/write helpers for state.json.
State is always read fresh from disk and written back immediately on any change
so that restarts never lose progress.
"""

import json
import logging
from datetime import datetime, timezone

STATE_PATH = "state.json"

logger = logging.getLogger(__name__)


def load_state() -> dict:
    """
    Read state.json and return the parsed dict.
    Returns {} (empty dict) if the file is missing, empty, or corrupted.
    Logs a warning on corruption so the caller can decide to reset.
    """
    try:
        with open(STATE_PATH, "r") as f:
            raw = f.read().strip()
            if not raw:
                return {}
            return json.loads(raw)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        logger.warning(f"[state] state.json is corrupted ({e}). Resetting to empty state.")
        return {}


def save_state(state: dict) -> None:
    """Write the given dict to state.json, pretty-printed."""
    try:
        with open(STATE_PATH, "w") as f:
            json.dump(state, f, indent=2, default=str)
    except OSError as e:
        logger.error(f"[state] Failed to write state.json: {e}")


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
