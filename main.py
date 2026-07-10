"""Telegram personal userbot — entry point."""

from __future__ import annotations

import asyncio
import os
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

# Minimal HTTP body so Koyeb TCP/HTTP health checks on PORT pass.
_HEALTH_RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/plain\r\n"
    b"Content-Length: 2\r\n"
    b"Connection: close\r\n"
    b"\r\n"
    b"ok"
)


async def start_health_server(port: int) -> asyncio.AbstractServer:
    """Listen on 0.0.0.0:PORT so cloud platforms (Koyeb Web) stay healthy."""

    async def _handle(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            await asyncio.wait_for(reader.read(1024), timeout=2.0)
        except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError):
            pass
        try:
            writer.write(_HEALTH_RESPONSE)
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(_handle, "0.0.0.0", port)
    print(f"Health check listening on 0.0.0.0:{port}")
    return server


async def main() -> None:
    config = load_config(ROOT)
    db = Database(
        config.db_path,
        turso_url=config.turso_database_url,
        turso_token=config.turso_auth_token,
    )
    await db.connect()
    await db.init_schema()
    if db.using_turso:
        print("Database: Turso (remote — survives Koyeb rebuilds)")
    else:
        print(f"Database: local SQLite ({config.db_path})")

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

    # Koyeb Web services probe PORT (default 8000). Without this, instance dies.
    port = int(os.getenv("PORT", "8000"))
    health_server = await start_health_server(port)

    await client.start()
    me = await client.get_me()
    name = me.first_name or "User"
    username = f"@{me.username}" if me.username else "(no username)"
    print(f"Logged in as {name} {username} (id={me.id})")
    print("Userbot is running.\n")

    # Start background tasks registered by plugins
    for task_factory in getattr(client, "_userbot_bg_tasks", []):
        asyncio.create_task(task_factory())

    try:
        await client.run_until_disconnected()
    finally:
        health_server.close()
        await health_server.wait_closed()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
