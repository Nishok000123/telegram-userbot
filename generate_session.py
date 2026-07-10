"""Generate a Telethon SESSION_STRING for cloud deploy (Koyeb, etc.).

Run this ONCE on your PC (not on Koyeb):

    python generate_session.py

Then paste the printed string into Koyeb as env var SESSION_STRING.
Never share this string — it is full access to your Telegram account.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from telethon import TelegramClient
from telethon.sessions import StringSession

from bot.config import load_config


async def main() -> None:
    config = load_config(ROOT)
    client = TelegramClient(StringSession(), config.api_id, config.api_hash)

    print("Log in once to create a session string for Koyeb.\n")
    await client.start()
    session_string = client.session.save()
    me = await client.get_me()
    await client.disconnect()

    print("\n" + "=" * 60)
    print("SUCCESS — copy everything below into Koyeb env SESSION_STRING:")
    print("=" * 60)
    print(session_string)
    print("=" * 60)
    print(f"\nLogged in as: {me.first_name} (id={me.id})")
    print("Keep this secret. Do not commit it to GitHub.")


if __name__ == "__main__":
    asyncio.run(main())
