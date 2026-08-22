<div align="center">

# 🤖 OmniBot
### The All-in-One Production Discord Bot

Moderation • AutoMod • Logging • Tickets • Giveaways • Leveling • Economy • Music • Fun

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discordpy.readthedocs.io)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

</div>

---

## ✨ Features

| Module | What it does |
|---|---|
| 🔨 **Moderation** | ban, unban, kick, softban, mute/timeout, warn system, purge, lock/lockdown, slowmode, nicknames, case logging, mod history |
| 🛡️ **AutoMod** | word filter, invite/link blocking, mention/caps/emoji limits, configurable punishments (delete → mute → kick → ban) |
| 📜 **Logging** | message edit/delete, join/leave, bans, voice, channel/role create/delete, nickname changes — each routed to its own channel |
| 🧰 **Utility** | ping, userinfo, serverinfo, avatar, banner, roleinfo, channelinfo, botinfo, reminders, polls, snipe/editsnipe, AFK, suggestions |
| 🪙 **Economy** | balance, daily, weekly, work, pay, coinflip, slots, leaderboard, admin money tools |
| 📈 **Leveling** | XP on messages (anti-spam cooldown), rank card with progress bar, server XP leaderboard, level-up announcements |
| 🎫 **Tickets** | button-opened private channels, claim, close with text transcript, per-user limits |
| 🎉 **Giveaways** | button entry, timed auto-end, reroll, active list — restart-safe |
| 👋 **Welcome** | customizable welcome/leave messages with variables, autorole |
| 🎭 **Roles** | self-assignable roles via dropdown menu |
| 🎲 **Fun** | 8ball, rps, ship, rate, dice, coin, counting game with cheat detection, custom tags |
| 🎵 **Music** | play/pause/skip/stop/queue/volume/loop/shuffle/nowplaying (yt-dlp + FFmpeg) |
| ⚙️ **Config** | per-server prefix, language, module toggles, channel settings |
| ⏰ **Scheduler** | reminders + temp actions, all database-backed — survives restarts |

**77 commands** across 17 modules. Every module can be enabled/disabled per server.

## 🌐 Multi-Language

Built-in **English** and **Persian (فارسی)**. All bot text lives in `config/messages.yml` — add your own language by copying a block. Set per server:

```
!config language fa
```

## 📁 Project Structure

```
OmniBot/
├── main.py                  # entry point — run this
├── requirements.txt
├── .env.example             # copy to .env, add your token
├── Dockerfile
├── config/                  # ⚙️ ALL configuration lives here
│   ├── config.yml           #    bot settings, branding, module defaults
│   └── messages.yml         #    every message/translation (en + fa)
├── bot/
│   ├── core/
│   │   ├── bot.py           # OmniBot client class
│   │   ├── config.py        # YAML config loader + i18n
│   │   └── database.py      # async SQLite layer (all persistence)
│   ├── utils/
│   │   ├── embeds.py        # branded embed builders
│   │   ├── checks.py        # permission + module checks
│   │   ├── timeutil.py      # duration parsing/formatting
│   │   └── views.py         # pagination + confirm buttons
│   └── cogs/                # 17 feature modules
│       ├── moderation.py  automod.py     logging.py
│       ├── utility.py     economy.py     leveling.py
│       ├── tickets.py     giveaways.py   welcome.py
│       ├── roles.py       fun.py         music.py
│       ├── config.py      help.py        scheduler.py
│       ├── owner.py       error_handler.py
└── data/                    # runtime: SQLite DB + logs (auto-created)
```

## 🚀 Quick Start

### 1. Create a bot application
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. **New Application** → give it a name
3. **Bot** tab → **Reset Token** → copy the token
4. Enable these **Privileged Gateway Intents**:
   - ✅ SERVER MEMBERS INTENT
   - ✅ MESSAGE CONTENT INTENT
5. **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`, permissions `Administrator` (or fine-tune), open the URL to invite the bot

### 2. Run it

```bash
git clone https://github.com/mohammad1390555/OmniBot.git
cd OmniBot

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and paste your bot token

python main.py
```

### 3. Configure in Discord

```
!help                  # interactive help menu
!config                # view server config
!config prefix ?       # change prefix
!config language fa    # switch to Persian
!config modules music false   # disable a module
!setlog message #logs  # route message logs
!ticket panel          # post the ticket button
```

### Docker (optional)

```bash
docker build -t omnibot .
docker run -d --name omnibot \
  -e DISCORD_TOKEN=*** \
  -v omnibot-data:/app/data \
  omnibot
```

## 🎵 Enabling Music

Music needs two extras:

```bash
pip install yt-dlp PyNaCl
# FFmpeg must be installed and on PATH:
#   Ubuntu/Debian: sudo apt install ffmpeg
#   Windows:       winget install ffmpeg
```

## ⚙️ Configuration

Everything is configured in the **`config/`** folder:

- **`config/config.yml`** — token fallback, prefix, presence, branding/color, intents, database path, and default settings for every module (automod rules, leveling XP curve, economy amounts, ticket behavior, music limits...)
- **`config/messages.yml`** — every single message the bot sends, in every language

Per-server overrides (prefix, language, channels, module toggles, automod words...) are stored in the database and managed through Discord commands.

## 🔒 Security Notes

- Never commit your `.env` — it's gitignored
- The token in `config.yml` is optional; `.env` always wins
- Owner-only commands (`reload`, `shutdown`, `guilds`, `sync`) are locked to the application owner

## 📄 License

MIT — do whatever you want with it.

---

<div align="center">

Made with ❤️ by [mohammad1390555](https://github.com/mohammad1390555)

</div>
