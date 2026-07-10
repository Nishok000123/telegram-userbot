"""Ping and alive status."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bot.utils.decorators import command, edit_or_reply, register_help

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database

STARTED_AT = datetime.now(timezone.utc)


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    # help entries registered in help.py for Basics

    @command(client, config, r"ping$")
    async def ping_cmd(event) -> None:
        start = time.perf_counter()
        await event.edit("Pong…")
        ms = (time.perf_counter() - start) * 1000
        await event.edit(f"**Pong!** `{ms:.0f} ms`")

    @command(client, config, r"alive$")
    async def alive_cmd(event) -> None:
        me = await client.get_me()
        uptime = datetime.now(timezone.utc) - STARTED_AT
        hours, rem = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(rem, 60)
        name = me.first_name or "User"
        username = f"@{me.username}" if me.username else "—"
        text = (
            "**Userbot is alive**\n"
            f"• Account: {name} ({username})\n"
            f"• Uptime: `{hours}h {minutes}m {seconds}s`\n"
            f"• Prefix: `{config.cmd_prefix}`"
        )
        await edit_or_reply(event, text)
