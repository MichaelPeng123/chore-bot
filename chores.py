"""
chores.py — Rotation logic and assignment generation.
3 roommates, 3 chores, 1 chore per person per week. Rotates each cycle.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def get_assignments(roommates: list[dict], chores: list[str], cycle_number: int) -> list[dict]:
    """
    Build a fresh list of assignment dicts for the given cycle.

    Rotation formula: chore_index = (roommate_index + cycle_number) % len(chores)
    Shifts every roommate one chore forward each cycle.
    """
    assignments = []
    for i, roommate in enumerate(roommates):
        chore_index = (i + cycle_number) % len(chores)
        assignments.append({
            "roommate": roommate["name"],
            "discord_user_id": roommate["discord_user_id"],
            "chore": chores[chore_index],
            "completed": False,
            "completed_at": None,
        })
    return assignments


def build_new_cycle(config: dict, cycle_number: int) -> dict:
    """
    Create a complete state dict for a brand-new cycle.
    The cycle runs Sunday through Saturday (ends Saturday at 23:59).
    """
    tz = ZoneInfo(config["timezone"])
    now = datetime.now(tz)
    days_until_saturday = (5 - now.weekday()) % 7 or 7
    cycle_end = (now + timedelta(days=days_until_saturday)).replace(
        hour=23, minute=59, second=0, microsecond=0
    )

    assignments = get_assignments(config["roommates"], config["chores"], cycle_number)

    return {
        "cycle_number": cycle_number,
        "cycle_start": now.isoformat(),
        "cycle_end": cycle_end.isoformat(),
        "reminder_sent": False,
        "assignments": assignments,
    }


def format_assignment_message(state: dict) -> str:
    """Build the human-readable assignment announcement posted to Discord."""
    cycle_end = state["cycle_end"]
    try:
        end_dt = datetime.fromisoformat(cycle_end)
        due_str = end_dt.strftime("%b %-d")
        week_str = datetime.fromisoformat(state["cycle_start"]).strftime("%Y-%m-%d")
    except ValueError:
        due_str = cycle_end
        week_str = "?"

    lines = [f"🧹 CHORE DAY! Week of {week_str}, due by Saturday {due_str} at 11:59pm\n"]
    for a in state["assignments"]:
        lines.append(f"<@{a['discord_user_id']}> → {a['chore']}")
    lines.append('\nType "chore complete" when you\'re done!')
    return "\n".join(lines)


def format_history_message(history: list[dict]) -> str:
    """Build the history message for the !history command."""
    if not history:
        return "No completed cycles yet."

    lines = [f"**Chore history (last {len(history)} cycle{'s' if len(history) != 1 else ''}):**"]
    for entry in history:
        try:
            start = datetime.fromisoformat(str(entry["cycle_start"])).strftime("%b %-d")
            end = datetime.fromisoformat(str(entry["cycle_end"])).strftime("%b %-d")
        except (ValueError, TypeError):
            start = end = "?"
        lines.append(f"\nCycle {entry['cycle_number']} — {start} to {end}")
        for a in entry["assignments"]:
            icon = "✅" if a.get("completed") else "⏳"
            lines.append(f"{icon} {a['roommate']} → {a['chore']}")
    return "\n".join(lines)


def format_status_message(state: dict) -> str:
    """Build the status message for the !status command."""
    lines = ["**Current chore assignments:**\n"]
    for a in state["assignments"]:
        icon = "✅" if a["completed"] else "⏳"
        lines.append(f"{icon} <@{a['discord_user_id']}> → {a['chore']}")
    return "\n".join(lines)
