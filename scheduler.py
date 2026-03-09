"""
scheduler.py — APScheduler jobs: assign_chores and send_reminder.
Jobs are registered once at startup and run on their configured intervals.
"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import chores
import state as state_module

logger = logging.getLogger(__name__)


def setup_scheduler(bot, config: dict, tz_str: str) -> AsyncIOScheduler:
    """
    Create and configure the APScheduler instance with all jobs.
    Returns the scheduler (not yet started — bot.py calls scheduler.start()).

    Args:
        bot:    The discord.Client instance (used to send messages).
        config: Loaded config dict.
        tz_str: Timezone string from config, e.g. "America/Los_Angeles".
    """
    scheduler = AsyncIOScheduler(timezone=tz_str)

    # --- Job 1: Assign chores every cycle_days at 08:00 ---
    scheduler.add_job(
        assign_chores,
        trigger=CronTrigger(hour=8, minute=0, timezone=tz_str),
        args=[bot, config],
        id="assign_chores",
        # Run every cycle_days days by using an interval trigger alternative below.
        # CronTrigger fires daily; assign_chores() checks internally if a new cycle is due.
        name="Assign chores",
        misfire_grace_time=300,
    )

    # --- Job 2: Send reminder daily at 09:00 ---
    scheduler.add_job(
        send_reminder,
        trigger=CronTrigger(hour=9, minute=0, timezone=tz_str),
        args=[bot, config],
        id="send_reminder",
        name="Send chore reminder",
        misfire_grace_time=300,
    )

    return scheduler


async def assign_chores(bot, config: dict) -> None:
    """
    Scheduled job — runs daily at 08:00 and starts a new cycle when the current one has ended.

    Steps:
    1. Load state.json.
    2. If current cycle is still active, do nothing.
    3. Otherwise: increment cycle_number, build new cycle, save, post announcement.
    """
    current_state = state_module.load_state()

    # If a valid cycle is still running, skip this tick
    if state_module.is_active_cycle(current_state):
        logger.info("[scheduler] assign_chores: current cycle still active, skipping.")
        return

    # Archive the completed cycle before starting a new one
    if current_state:
        state_module.archive_cycle(current_state)

    # Determine next cycle number (default to 1 if no previous state)
    prev_cycle = current_state.get("cycle_number", 0)
    new_cycle_number = prev_cycle + 1

    # Build and persist the new cycle
    new_state = chores.build_new_cycle(config, new_cycle_number)
    state_module.save_state(new_state)
    logger.info(f"[scheduler] Started cycle {new_cycle_number}.")

    # Post announcement to the configured Discord channel
    await _post_assignment_message(bot, new_state)


async def send_reminder(bot, config: dict) -> None:
    """
    Scheduled job — runs daily at 09:00 and posts a reminder if today is the reminder day.

    Steps:
    1. Load state.json.
    2. Check if today == cycle_end - remind_before_days.
    3. If reminder already sent, skip.
    4. If any chores incomplete, mention those users and set reminder_sent = True.
    """
    current_state = state_module.load_state()

    if not state_module.is_active_cycle(current_state):
        return  # No active cycle, nothing to remind about

    if current_state.get("reminder_sent", False):
        logger.info("[scheduler] send_reminder: reminder already sent this cycle.")
        return

    # Check if today is the reminder day
    try:
        cycle_end = datetime.fromisoformat(current_state["cycle_end"])
        if cycle_end.tzinfo is None:
            cycle_end = cycle_end.replace(tzinfo=timezone.utc)
    except (ValueError, KeyError):
        logger.error("[scheduler] send_reminder: could not parse cycle_end.")
        return

    remind_before_days = config.get("remind_before_days", 1)
    now = datetime.now(timezone.utc)
    days_until_end = (cycle_end.date() - now.date()).days

    if days_until_end != remind_before_days:
        return  # Not the reminder day yet

    # Gather incomplete assignments
    pending = state_module.incomplete_assignments(current_state)
    if not pending:
        logger.info("[scheduler] send_reminder: all chores already complete, no reminder needed.")
        return

    # Build reminder message
    mentions = " ".join(f"<@{a['discord_user_id']}>" for a in pending)
    message = f"⏰ Chores are due tomorrow!\nStill pending: {mentions}"

    # Send to channel and mark reminder as sent
    await _send_to_channel(bot, message)
    current_state["reminder_sent"] = True
    state_module.save_state(current_state)
    logger.info("[scheduler] Reminder sent.")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _post_assignment_message(bot, state: dict) -> None:
    """Format and send the assignment announcement to the configured channel."""
    message = chores.format_assignment_message(state)
    await _send_to_channel(bot, message)


async def _send_to_channel(bot, message: str) -> None:
    """
    Fetch the configured channel by ID and send a message.
    Logs an error instead of crashing if the API call fails.
    """
    try:
        channel = bot.get_channel(bot.channel_id)
        if channel is None:
            # Channel not in cache yet — fetch from API
            channel = await bot.fetch_channel(bot.channel_id)
        await channel.send(message)
    except Exception as e:
        logger.error(f"[scheduler] Failed to send message to channel: {e}")
