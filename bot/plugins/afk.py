"""AFK mode — auto-reply to DMs and mentions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from telethon import events

from bot.utils.decorators import command, edit_or_reply, register_help
from bot.utils.timeparse import format_local, from_iso, to_iso, utc_now

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database

AFK_ON = "afk_on"
AFK_REASON = "afk_reason"
AFK_SINCE = "afk_since"

# Avoid spamming the same person repeatedly
_last_reply: dict[int, float] = {}
_COOLDOWN_SEC = 60


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    register_help(
        client,
        "AFK",
        [
            f"{config.cmd_prefix}afk [reason] — go AFK",
            f"{config.cmd_prefix}unafk — turn AFK off",
        ],
    )

    @command(client, config, r"afk(?:\s+(.+))?$")
    async def afk_cmd(event) -> None:
        reason = (event.pattern_match.group(1) or "AFK").strip()
        now = utc_now()
        await db.set_setting(AFK_ON, "1")
        await db.set_setting(AFK_REASON, reason)
        await db.set_setting(AFK_SINCE, to_iso(now))
        await edit_or_reply(event, f"**AFK on**\nReason: {reason}")

    @command(client, config, r"unafk$")
    async def unafk_cmd(event) -> None:
        await db.set_setting(AFK_ON, "0")
        await db.delete_setting(AFK_REASON)
        await db.delete_setting(AFK_SINCE)
        await edit_or_reply(event, "**AFK off** — welcome back.")

    @client.on(events.NewMessage(incoming=True))
    async def afk_watcher(event) -> None:
        if await db.get_setting(AFK_ON, "0") != "1":
            return

        # Only private chats or mentions
        is_private = event.is_private
        mentioned = bool(event.mentioned)
        if not (is_private or mentioned):
            return

        # Don't reply to yourself / bots / service messages
        sender = await event.get_sender()
        if sender is None:
            return
        if getattr(sender, "bot", False) or getattr(sender, "is_self", False):
            return

        sender_id = event.sender_id or 0
        now_ts = utc_now().timestamp()
        last = _last_reply.get(sender_id, 0)
        if now_ts - last < _COOLDOWN_SEC:
            return
        _last_reply[sender_id] = now_ts

        reason = await db.get_setting(AFK_REASON, "AFK")
        since = await db.get_setting(AFK_SINCE)
        since_txt = ""
        if since:
            try:
                since_txt = f"\nSince: {format_local(from_iso(since))}"
            except ValueError:
                since_txt = ""
        await event.reply(f"**I'm currently AFK.**\nReason: {reason}{since_txt}")
