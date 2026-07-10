"""Telegram personal userbot — entry point."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is on the path when run as a script
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.client import create_client
from bot.config import load_config
from bot.loader import load_plugins
from bot.storage.db import Database


async def main() -> None:
    config = load_config(ROOT)
    db = Database(config.db_path)
    await db.connect()
    await db.init_schema()

    client = create_client(config)
    load_plugins(client, db, config)

    print("Starting userbot…")
    if config.session_string:
        print("Using SESSION_STRING (cloud / Koyeb mode).")
    else:
        print("First run: enter your phone number and login code when asked.")
        print("Tip for Koyeb: run python generate_session.py and set SESSION_STRING.")
    print("After login, open Saved Messages in Telegram and type .help")
    print("Press Ctrl+C to stop.\n")

    await client.start()
    me = await client.get_me()
    name = me.first_name or "User"
    username = f"@{me.username}" if me.username else "(no username)"
    print(f"Logged in as {name} {username} (id={me.id})")
    print("Userbot is running.\n")

    # Start background tasks registered by plugins
    for task_factory in getattr(client, "_userbot_bg_tasks", []):
        asyncio.create_task(task_factory())

    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
