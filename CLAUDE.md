# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Bot

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python bot.py
```

## Environment Setup

Copy `.env.example` (or create `.env`) with:
```
DISCORD_TOKEN=your_bot_token
CHANNEL_ID=your_channel_id
```

Configure `config.json` with roommates (name + discord_user_id), chores list, `cycle_days`, `remind_before_days`, and `timezone`.

## Architecture

Five modules with clear separation of concerns:

- **bot.py** — Entry point. Loads env/config, handles Discord events (`on_ready`, `on_message`), detects chore completion keywords ("done", "finished", "completed", "chore complete"), and dispatches `!status`, `!mychore`, `!help` commands.
- **chores.py** — Rotation logic. Assigns chores via `chore_index = (roommate_index + cycle_number) % len(chores)`, ensuring each person rotates through different chores each cycle.
- **scheduler.py** — Two APScheduler jobs: `assign_chores` at 08:00 (starts new cycle when current expires) and `send_reminder` at 09:00 (mentions users with incomplete chores the day before cycle ends).
- **state.py** — JSON persistence. Reads/writes `state.json` which tracks current cycle number, start/end times, assignments, and per-assignment completion status.
- **config.py** — Validates and loads `config.json`.

## State Persistence

`state.json` is the runtime database and is excluded from git. On platforms with ephemeral filesystems (Railway, Render), this file will be lost on restart — the bot will start a new Cycle 1 each time. For persistent deployments, a database-backed state store would be needed.

## No Automated Tests

There is no test suite. Manual testing requires a Discord test server. The bot operates only in the channel specified by `CHANNEL_ID`.
