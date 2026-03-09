"""
bot.py — Entry point. Sets up the Discord client, event listeners, and starts the scheduler.

Run with:
    python bot.py
"""

import logging
import os

import discord
from dotenv import load_dotenv

import chores
import config as config_module
import scheduler as scheduler_module
import state as state_module

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load environment and config
# ---------------------------------------------------------------------------
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

if not DISCORD_TOKEN or CHANNEL_ID == 0:
    raise SystemExit("[bot] ERROR: DISCORD_TOKEN and CHANNEL_ID must be set in .env")

config = config_module.load_config()

# ---------------------------------------------------------------------------
# Discord client setup
# ---------------------------------------------------------------------------
# Enable the message_content intent so on_message can read message text
intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)
bot.channel_id = CHANNEL_ID  # Attach channel_id so scheduler helpers can reach it

# Keywords that count as "chore complete" acknowledgements
COMPLETE_KEYWORDS = {"chore complete", "done", "finished", "completed"}

# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@bot.event
async def on_ready():
    """
    Fires once after the bot has connected and is ready to receive events.

    Responsibilities:
    - Log that we are online.
    - Check for an active cycle; create a new one and post assignments if none exists.
    - Start the APScheduler.
    """
    logger.info(f"[bot] Logged in as {bot.user} (id: {bot.user.id})")

    # --- Initialise database ---
    state_module.init_db()

    # --- Bootstrap: ensure there is an active cycle ---
    current_state = state_module.load_state()
    if not state_module.is_active_cycle(current_state):
        logger.info("[bot] No active cycle found — starting cycle 1.")
        prev_cycle = current_state.get("cycle_number", 0)
        new_state = chores.build_new_cycle(config, prev_cycle + 1)
        state_module.save_state(new_state)

        # Post the first assignment message immediately
        try:
            channel = bot.get_channel(CHANNEL_ID) or await bot.fetch_channel(CHANNEL_ID)
            await channel.send(chores.format_assignment_message(new_state))
        except Exception as e:
            logger.error(f"[bot] Could not post initial assignment: {e}")
    else:
        logger.info(f"[bot] Resuming active cycle {current_state.get('cycle_number')}.")

    # --- Start scheduler ---
    scheduler = scheduler_module.setup_scheduler(bot, config, config["timezone"])
    scheduler.start()
    logger.info("[bot] Scheduler started.")


@bot.event
async def on_message(message: discord.Message):
    """
    Fires on every message in any channel the bot can see.

    Handles:
    - Ignoring bot messages and messages outside the configured channel.
    - Detecting chore completion keywords.
    - !status, !mychore, !help commands.
    """
    # Ignore messages from bots (including ourselves)
    if message.author.bot:
        return

    # Only process messages in the configured channel
    if message.channel.id != CHANNEL_ID:
        return

    content = message.content.lower().strip()

    # --- Commands ---
    if content == "!help":
        await _handle_help(message)
        return

    if content == "!status":
        await _handle_status(message)
        return

    if content == "!mychore":
        await _handle_mychore(message)
        return

    if content == "!history":
        await _handle_history(message)
        return

    # --- Chore completion detection ---
    # Check if the message contains any of the completion keywords
    if any(keyword in content for keyword in COMPLETE_KEYWORDS):
        await _handle_chore_complete(message)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def _handle_help(message: discord.Message) -> None:
    """Reply with a list of available commands."""
    help_text = (
        "**Chore Bot Commands**\n"
        "`!status`  — Show current chore assignments and completion status\n"
        "`!mychore` — Show your current chore assignment\n"
        "`!history` — Show the last 5 completed cycles\n"
        "`!help`    — Show this help message\n\n"
        "Say `chore complete`, `done`, `finished`, or `completed` to mark your chore done."
    )
    await message.channel.send(help_text)


async def _handle_status(message: discord.Message) -> None:
    """Post a status summary of all assignments for the current cycle."""
    current_state = state_module.load_state()
    if not state_module.is_active_cycle(current_state):
        await message.channel.send("No active chore cycle right now.")
        return
    await message.channel.send(chores.format_status_message(current_state))


async def _handle_mychore(message: discord.Message) -> None:
    """Reply with the calling user's current chore assignment."""
    current_state = state_module.load_state()
    if not state_module.is_active_cycle(current_state):
        await message.channel.send("No active chore cycle right now.")
        return

    user_id = str(message.author.id)
    for assignment in current_state.get("assignments", []):
        if assignment["discord_user_id"] == user_id:
            status = "✅ completed" if assignment["completed"] else "⏳ pending"
            await message.channel.send(
                f"<@{user_id}> your chore is: **{assignment['chore']}** — {status}"
            )
            return

    # User is not in this cycle's assignments — silently ignore or inform
    await message.channel.send("You don't have a chore assigned this cycle.")


async def _handle_history(message: discord.Message) -> None:
    """Post the last 5 completed cycles and their assignment outcomes."""
    history = state_module.load_history()
    await message.channel.send(chores.format_history_message(history))


async def _handle_chore_complete(message: discord.Message) -> None:
    """
    Mark the calling user's chore as complete.

    Possible outcomes:
    - Assignment found and not yet complete → mark complete, confirm, check for all-done.
    - Assignment found but already complete → tell them.
    - User not in assignments → silently ignore.
    """
    current_state = state_module.load_state()
    if not state_module.is_active_cycle(current_state):
        return  # No active cycle — nothing to complete

    user_id = str(message.author.id)
    found, already_complete = state_module.mark_assignment_complete(current_state, user_id)

    if not found:
        return  # User not in this cycle — ignore silently

    if already_complete:
        await message.channel.send(
            f"<@{user_id}> You already completed your chore this cycle!"
        )
        return

    # Reload state after write (mark_assignment_complete already saved it)
    current_state = state_module.load_state()

    await message.channel.send(f"✅ Nice work <@{user_id}>! Chore marked as complete.")

    # Check if everyone is done
    if state_module.all_complete(current_state):
        await message.channel.send(
            "🎉 All chores done this cycle — great work everyone!"
        )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
