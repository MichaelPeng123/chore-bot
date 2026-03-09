"""
chores.py — Rotation logic and assignment generation.
The rotation formula ensures each roommate gets a different chore every cycle.
"""

from datetime import datetime, timedelta, timezone


def get_assignments(roommates: list[dict], chores: list[str], cycle_number: int) -> list[dict]:
    """
    Build a fresh list of assignment dicts for the given cycle.

    Rotation formula: chore_index = (roommate_index + cycle_number) % len(chores)
    This shifts every roommate one chore forward each cycle.

    Args:
        roommates:    List of roommate dicts from config.json.
        chores:       List of chore strings from config.json.
        cycle_number: Current cycle number (starts at 1, increments each cycle).

    Returns:
        List of assignment dicts ready to be stored in state.json.
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

    The cycle starts now (rounded to current time) and ends cycle_days later at 08:00.

    Args:
        config:       Loaded config dict.
        cycle_number: The cycle number to assign.

    Returns:
        A state dict ready to be passed to save_state().
    """
    now = datetime.now(timezone.utc)
    cycle_days = config["cycle_days"]

    # Cycle ends cycle_days from now at 08:00 local time (stored as UTC here for simplicity)
    cycle_end = now + timedelta(days=cycle_days)
    # Snap end time to 08:00 of that day
    cycle_end = cycle_end.replace(hour=8, minute=0, second=0, microsecond=0)

    assignments = get_assignments(config["roommates"], config["chores"], cycle_number)

    return {
        "cycle_number": cycle_number,
        "cycle_start": now.isoformat(),
        "cycle_end": cycle_end.isoformat(),
        "reminder_sent": False,
        "assignments": assignments,
    }


def format_assignment_message(state: dict) -> str:
    """
    Build the human-readable assignment announcement posted to Discord.

    Example output:
        🧹 New chore cycle! Due by 2026-03-09 at 11:59pm

        <@111> → Vacuum living room
        <@222> → Clean bathroom

        Type "chore complete" when you're done!
    """
    cycle_end = state["cycle_end"]
    # Parse and format the due date nicely
    try:
        end_dt = datetime.fromisoformat(cycle_end)
        due_str = end_dt.strftime("%Y-%m-%d")
    except ValueError:
        due_str = cycle_end

    lines = [f"🧹 New chore cycle! Due by {due_str} at 11:59pm\n"]
    for a in state["assignments"]:
        lines.append(f"<@{a['discord_user_id']}> → {a['chore']}")
    lines.append('\nType "chore complete" when you\'re done!')
    return "\n".join(lines)


def format_history_message(history: list[dict]) -> str:
    """
    Build the history message for the !history command.

    Example output:
        **Chore history (last 3 cycles):**

        Cycle 3 — Mar 5 to Mar 8
        ✅ User1 → Vacuum living room
        ⏳ User2 → Clean bathroom

        Cycle 2 — Mar 2 to Mar 5
        ✅ User1 → Take out trash
        ✅ User2 → Vacuum living room
    """
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
    """
    Build the status message for the !status command.

    Each line shows ✅ or ⏳ next to the roommate's mention and chore.
    """
    lines = ["**Current chore assignments:**\n"]
    for a in state["assignments"]:
        icon = "✅" if a["completed"] else "⏳"
        lines.append(f"{icon} <@{a['discord_user_id']}> → {a['chore']}")
    return "\n".join(lines)
