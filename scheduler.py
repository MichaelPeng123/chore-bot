"""
scheduler.py — APScheduler jobs: assign_chores and send_reminder.
Both jobs fire on Sundays only — Sunday is the authoritative CHORE DAY.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import chores
import state as state_module

logger = logging.getLogger(__name__)


def setup_scheduler(bot, config: dict, tz_str: str) -> AsyncIOScheduler:
    """
    Create and configure the APScheduler instance with all jobs.
    Returns the scheduler (not yet started — bot.py calls scheduler.start()).
    """
    scheduler = AsyncIOScheduler(timezone=tz_str)

    # Job 1: Assign chores every Sunday at 08:00
    scheduler.add_job(
        assign_chores,
        trigger=CronTrigger(day_of_week="sun", hour=8, minute=0, timezone=tz_str),
        args=[bot, config],
        id="assign_chores",
        name="Assign chores",
        misfire_grace_time=300,
    )

    # Job 2: Send reminder every Sunday at 09:00
    scheduler.add_job(
        send_reminder,
        trigger=CronTrigger(day_of_week="sun", hour=9, minute=0, timezone=tz_str),
        args=[bot, config],
        id="send_reminder",
        name="Send chore reminder",
        misfire_grace_time=300,
    )

    return scheduler


async def assign_chores(bot, config: dict) -> None:
    """
    Scheduled job — runs every Sunday at 08:00.
    Archives the previous cycle and starts a new one.
    """
    current_state = state_module.load_state()

    if current_state:
        state_module.archive_cycle(current_state)

    prev_cycle = current_state.get("cycle_number", 0)
    new_cycle_number = prev_cycle + 1

    new_state = chores.build_new_cycle(config, new_cycle_number)
    state_module.save_state(new_state)
    logger.info(f"[scheduler] Started cycle {new_cycle_number}.")

    await _post_assignment_message(bot, new_state)


async def send_reminder(bot, config: dict) -> None:
    """
    Scheduled job — runs every Sunday at 09:00.
    Sends a reminder to users who haven't completed their chores yet.
    Uses reminder_sent flag to prevent duplicate sends on bot restart mid-Sunday.
    """
    current_state = state_module.load_state()

    if not state_module.is_active_cycle(current_state):
        return

    if current_state.get("reminder_sent", False):
        logger.info("[scheduler] send_reminder: reminder already sent this cycle.")
        return

    pending = state_module.incomplete_assignments(current_state)
    if not pending:
        logger.info("[scheduler] send_reminder: all chores already complete, no reminder needed.")
        return

    mentions = " ".join(f"<@{a['discord_user_id']}>" for a in pending)
    message = f"⏰ Don't forget — chores are due this Saturday!\nStill pending: {mentions}"

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
            channel = await bot.fetch_channel(bot.channel_id)
        await channel.send(message)
    except Exception as e:
        logger.error(f"[scheduler] Failed to send message to channel: {e}")
