# Discord Task Bot

A fully-featured Discord task management bot built with **discord.py 2.x**, **aiosqlite**, and a rich button/modal UI. Designed to run continuously on a **Raspberry Pi 5**.

---

## Features

| Feature | Details |
|---|---|
| **Create tasks** | `/task add` opens a modal form with title, description, priority, due date, and reminder |
| **List tasks** | `/task list` with optional status filter and paginated navigation |
| **View tasks** | `/task view <id>` — rich embed with priority, due date, reminder info |
| **Edit tasks** | ✏️ Edit button or in-line status drop-down on the detail view |
| **Mark done** | `/task done <id>` or the ✅ button |
| **Delete tasks** | `/task delete <id>` or the 🗑️ button — with confirmation |
| **Reminders** | Background loop fires reminders via channel message or DM |
| **Persistence** | SQLite database via aiosqlite — zero extra services required |

---

## Slash Commands

```
/task add           — Open the 'Create Task' modal
/task list          — Show your tasks (optional ?status filter)
/task view <id>     — Full detail view with action buttons
/task done <id>     — Quick-mark a task as done
/task delete <id>   — Delete a task (with confirmation prompt)
```

---

## Quick Start

### 1. Clone & set up Python environment

```bash
git clone <repo-url> discord-task-bot
cd discord-task-bot

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set DISCORD_TOKEN at minimum
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_TOKEN` | ✅ | — | Your bot's token from the Discord Developer Portal |
| `DISCORD_GUILD_ID` | ❌ | — | Set to your server ID for instant command sync during dev |
| `DATABASE_PATH` | ❌ | `data/tasks.db` | Path to the SQLite file |
| `REMINDER_POLL_SECONDS` | ❌ | `60` | How often (seconds) reminders are checked |
| `LOG_LEVEL` | ❌ | `INFO` | Python logging level |

### 3. Run

```bash
python main.py
```

---

## Raspberry Pi 5 — Persistent Deployment

### Install as a systemd service

```bash
# Copy the project to the Pi
scp -r . pi@raspberrypi.local:~/discord-task-bot

# SSH in
ssh pi@raspberrypi.local
cd ~/discord-task-bot

# Set up venv & install deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Copy & configure the service file
sudo cp deploy/discord-task-bot.service /etc/systemd/system/
sudo nano /etc/systemd/system/discord-task-bot.service  # adjust paths if needed

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable discord-task-bot
sudo systemctl start discord-task-bot

# Check logs
sudo journalctl -u discord-task-bot -f
```

### Keeping the bot up to date

```bash
cd ~/discord-task-bot
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart discord-task-bot
```

---

## Project Structure

```
discord-task-bot/
├── bot/
│   ├── __init__.py
│   ├── config.py          # pydantic-settings config (reads .env)
│   ├── core.py            # DiscordBot subclass & lifecycle
│   ├── database.py        # aiosqlite CRUD layer
│   ├── models.py          # Task dataclasses & enums
│   ├── cogs/
│   │   ├── tasks.py       # /task slash commands
│   │   └── reminders.py   # Background reminder loop
│   └── ui/
│       ├── embeds.py      # Embed builders
│       └── views.py       # Modals, buttons, selects, pagination
├── data/                  # SQLite DB stored here (auto-created)
├── deploy/
│   └── discord-task-bot.service  # systemd unit file
├── tests/
│   └── test_database.py
├── .env.example
├── main.py
├── pyproject.toml
└── requirements.txt
```

---

## Discord Developer Portal Setup

1. Go to <https://discord.com/developers/applications>
2. Create a new application → **Bot** section → **Reset Token** → copy to `.env`
3. Under **Privileged Gateway Intents**, no extra intents are needed (the bot uses slash commands only)
4. **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`, permissions:
   - Send Messages
   - Embed Links
   - Read Message History
   - Use External Emojis
5. Invite the bot using the generated URL

---

## Development

```bash
# Format
black .
isort .

# Tests
pytest
```

---

## Architecture Decisions

- **aiosqlite** — async SQLite wrapper; no extra database service needed — perfect for a Pi
- **discord.py 2.x** — native slash commands, modals, and component views
- **pydantic-settings** — typed & validated environment config
- **systemd** — process management on the Pi; auto-restarts on crashes, starts on boot
- **Ephemeral responses** — all task commands reply ephemerally to keep channels clean
