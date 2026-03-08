# Discord Chore Rotation Bot

A Discord bot that manages a rotating chore schedule for a roommate group.
Assigns chores every N days, listens for completion messages, and sends reminders.

## Setup

### 1. Clone the repo
```bash
git clone <your-repo-url>
cd chore-bot
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Fill in `.env`
```
DISCORD_TOKEN=your-bot-token-here
CHANNEL_ID=your-channel-id-here
```

### 4. Fill in `config.json`
Edit `config.json` with your roommates' names and Discord user IDs, your chore list,
cycle length, and timezone. Discord user IDs can be found by enabling Developer Mode
in Discord (Settings → Advanced → Developer Mode) then right-clicking a username.

### 5. Run the bot
```bash
python bot.py
```

The bot will post the first assignment message as soon as it comes online.

---

## Commands

| Command | Description |
|---|---|
| `!status` | Show all assignments with ✅/⏳ status |
| `!mychore` | Show your own current chore |
| `!help` | List available commands |

Say `chore complete`, `done`, `finished`, or `completed` to mark your chore as done.

---

## Deployment (Railway / Render)

1. Push your code to GitHub (`.env` and `state.json` are in `.gitignore` — do not commit them).
2. Create a new project on [Railway](https://railway.app) or [Render](https://render.com).
3. Connect your GitHub repo.
4. Add `DISCORD_TOKEN` and `CHANNEL_ID` as environment variables in the dashboard.
5. Set the start command to `python bot.py`.
6. Deploy.

> **Note:** `state.json` lives on the filesystem. On platforms with ephemeral storage
> (like Render's free tier), state resets on redeploy. For persistence, consider
> replacing `state.py` with a small database (SQLite, Redis, etc.).
