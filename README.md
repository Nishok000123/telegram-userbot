# Telethon Personal Userbot

A simple personal Telegram **userbot** that runs as **your account**.  
Type commands starting with `.` in any chat (Saved Messages is easiest).

**Includes:** AFK, notes, reminders, media download, snippets, and channel tools.  
**Does not include:** group moderation (ban/mute/warn/welcome).

---

## What you need

1. A Telegram account
2. Windows PC (these steps are for Windows)
3. Python 3.11 or newer

---

## Step 1 — Install Python

1. Open https://www.python.org/downloads/
2. Download Python 3.11+ and run the installer
3. **Important:** check **“Add python.exe to PATH”**
4. Finish install
5. Open **PowerShell** and check:

```powershell
python --version
```

You should see something like `Python 3.12.x`.

---

## Step 2 — Get API ID and API Hash

1. Open https://my.telegram.org in your browser
2. Log in with your phone number (same as Telegram)
3. Click **API development tools**
4. Create an app (any short name/description is fine)
5. Copy:
   - **App api_id** (a number)
   - **App api_hash** (a long string)

Keep these private. Do not share them.

---

## Step 3 — Configure the project

1. Open this folder:

```powershell
cd E:\telegram-userbot
```

2. Copy the example env file:

```powershell
copy .env.example .env
```

3. Open `.env` in Notepad and fill in your values:

```env
API_ID=12345678
API_HASH=paste_your_api_hash_here
CMD_PREFIX=.
```

Save the file.

---

## Step 4 — Install dependencies

In PowerShell:

```powershell
cd E:\telegram-userbot
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

When the virtual environment is active, your prompt usually starts with `(.venv)`.

---

## Step 5 — First login

```powershell
python main.py
```

Telegram will ask in the terminal for:

1. Your **phone number** (with country code, e.g. `+15551234567`)
2. The **login code** Telegram sends you
3. Your **2FA password** (only if you enabled cloud password)

After login succeeds, you will see something like:

```text
Logged in as YourName @username
Userbot is running.
```

Leave this window open while you use the userbot.

---

## Step 6 — Try it

1. Open Telegram → **Saved Messages**
2. Type:

```text
.help
```

Your message should change into the command list.

Try:

```text
.ping
.alive
.note add grocery milk and eggs
.note get grocery
```

---

## Daily use

Every time you want the userbot on:

```powershell
cd E:\telegram-userbot
.\.venv\Scripts\activate
python main.py
```

Stop it with `Ctrl+C`.

---

## Deploy on Koyeb (24/7)

Koyeb cannot ask for your phone code in a browser. You create a **session string on your PC once**, then paste it into Koyeb.

### A. Create SESSION_STRING on your PC

1. Make sure `.env` already has `API_ID` and `API_HASH`
2. Activate the venv and run:

```powershell
cd E:\telegram-userbot
.\.venv\Scripts\activate
python generate_session.py
```

3. Enter phone + login code (and 2FA if needed)
4. Copy the long `SESSION_STRING` printed at the end  
   **Never put this in GitHub. Never share it.**

### B. Push the project to GitHub

1. Create a **private** GitHub repo
2. Push this folder (do **not** commit `.env` or session files — they are already gitignored)

```powershell
cd E:\telegram-userbot
git add .
git commit -m "Add personal Telegram userbot"
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin main
```

### C. Create a Koyeb service

1. Open https://app.koyeb.com → **Create Service**
2. Choose **GitHub** and select your repo
3. **Service type:**
   - **Web** (recommended on Free) — app listens on `PORT` (default `8000`) for health checks
   - **or Worker** — no public port; disable health checks if the platform requires them
4. **Builder:** Dockerfile (auto-detected from `Dockerfile`)
5. **Port:** `8000` (Web only). Health check: TCP or HTTP `/` on port `8000`
6. Add environment variables:

| Name | Value |
|------|--------|
| `API_ID` | your api id number |
| `API_HASH` | your api hash |
| `SESSION_STRING` | the string from `generate_session.py` |
| `PORT` | `8000` (optional; Koyeb may set this) |
| `CMD_PREFIX` | `.` (optional) |
| `DATA_DIR` | `/data` (only if you attach a volume) |

7. **Persist notes + reminders** (optional, paid):
   - Koyeb **Volumes** do **not** work on Free / `eco-*` instances
   - Without a volume: login still works via `SESSION_STRING`; notes/reminders wipe on redeploy
8. Click **Deploy**
9. In the service logs you should see: `Health check listening on 0.0.0.0:8000` and `Userbot is running.`
10. In Telegram Saved Messages, type `.help`

### Koyeb notes

- **TCP health check failed on port 8000** = old image with no health server, or wrong port. Redeploy latest code; set port `8000`
- Notes / reminders / snippets / AFK / default channel = SQLite under `DATA_DIR`
- No volume = data wiped on every rebuild (login still OK)
- If login fails on Koyeb, regenerate `SESSION_STRING` on your PC and update the env var
- Run only **one** instance (two copies = session conflicts)

---

## Command cheat sheet

### Basics

| Command | Meaning |
|---------|---------|
| `.help` | Show all commands |
| `.ping` | Response time |
| `.alive` | Status / uptime |
| `.id` | Chat / user / channel IDs |

### AFK

| Command | Meaning |
|---------|---------|
| `.afk [reason]` | Turn AFK on (auto-replies to DMs/mentions) |
| `.unafk` | Turn AFK off |

### Notes

| Command | Meaning |
|---------|---------|
| `.note add name text` | Save a note |
| `.note get name` | Show a note |
| `.note list` | List notes |
| `.note del name` | Delete a note |

### Reminders

| Command | Meaning |
|---------|---------|
| `.remind 30m text` | Remind in 30 minutes |
| `.remind 2h text` | Remind in 2 hours |
| `.remind 1d text` | Remind in 1 day |
| `.remind list` | Pending reminders |
| `.remind del 3` | Cancel reminder `#3` |

Time forms: `10m`, `2h`, `1d`, `1h30m`, `90s`.

### Snippets

| Command | Meaning |
|---------|---------|
| `.snip add name text` | Save a quick reply |
| `.snip get name` | Paste it (replaces your command) |
| `.snip list` | List snippets |
| `.snip del name` | Delete a snippet |

### Media

| Command | Meaning |
|---------|---------|
| `.dl` | Reply to media → download into `data/downloads/` |

### Save Restricted (by post link)

Inspired by [VJ-Save-Restricted-Content](https://github.com/Nishok000123/VJ-Save-Restricted-Content). Uses **your** logged-in account (must already see the post).

| Command | Meaning |
|---------|---------|
| `.save https://t.me/channel/123` | Save one post into current chat |
| `.save https://t.me/c/ID/100-110` | Save a range (private channel) |
| `.save https://t.me/b/botuser/55` | Save from a bot chat link |
| `.join https://t.me/+xxxx` | Join private chat via invite (do this first if needed) |
| `.scancel` | Cancel a running `.save` batch |

Set `WAITING_TIME` in `.env` (seconds between posts) to reduce FloodWait risk.

### Channels

| Command | Meaning |
|---------|---------|
| `.channels` | List channels you can post to |
| `.cset @mychannel` | Set default channel |
| `.cpost Hello world` | Post to default channel |
| `.cpost @mychannel Hello` | Post to a specific channel |
| `.cpost` (reply to media) | Copy replied media to channel |
| `.cedit new text` | Reply to a channel post to edit it |
| `.cpin` / `.cunpin` | Reply to pin / unpin |
| `.cstat` / `.cstat @channel` | Channel info |
| `.csched 2h Hello later` | Schedule a post |
| `.cupload C:\path\photo.jpg` | Upload a local file |
| `.cupload` (reply to media) | Upload replied media to channel |

---

## Where your data is stored

| Path | Contents |
|------|----------|
| `.env` | API secrets (never share) |
| `sessions/userbot.session` | Login session (never share) |
| `data/userbot.db` | Notes, reminders, snippets, settings |
| `data/downloads/` | Files saved with `.dl` |

---

## Safety tips

- Never share `.env` or `*.session` — they give full access to your account
- Run **only one** copy of the userbot at a time (two copies cause “database is locked”)
- This is for **personal** use — no spam / mass messaging tools are included
- Channel commands only work on channels where you already have permission

---

## Common problems

**`Missing API credentials`**  
→ Copy `.env.example` to `.env` and put real `API_ID` / `API_HASH`.

**`database is locked`**  
→ Close other running `python main.py` windows, then start again.

**Commands do nothing**  
→ Make sure the terminal still shows “Userbot is running”, and that you typed the command yourself (outgoing message).

**Koyeb keeps restarting / AuthKeyError**  
→ `SESSION_STRING` is missing or invalid. Run `python generate_session.py` again on your PC and update the Koyeb env var.

**Notes disappear after Koyeb redeploy**  
→ Disk is ephemeral. Attach a volume at `/data` and set `DATA_DIR=/data`.

**Python not found**  
→ Reinstall Python and enable “Add to PATH”, then open a **new** PowerShell window.

---

## Project layout

```text
telegram-userbot/
  main.py
  requirements.txt
  .env.example
  bot/
    config.py
    client.py
    loader.py
    plugins/      ← commands live here
    storage/      ← SQLite
    utils/
  data/
  sessions/
```
