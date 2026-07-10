"""Remind later about a replied message (deep link)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot.utils.decorators import command, edit_or_reply, register_help
from bot.utils.peers import get_reply_or_fail, message_permalink
from bot.utils.timeparse import format_local, parse_duration, to_iso, utc_now

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    p = config.cmd_prefix
    register_help(
        client,
        "Later",
        [
            f"{p}later <when> [note] — reply to msg → remind + link",
        ],
    )

    @command(client, config, r"later(?:\s+(.*))?$")
    async def later_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        if not raw:
            await edit_or_reply(
                event,
                f"Usage (reply to a message):\n`{p}later 2h`\n`{p}later 30m follow up`",
            )
            return

        reply, err = await get_reply_or_fail(event)
        if err or reply is None:
            await edit_or_reply(event, err or "No reply.")
            return

        parts = raw.split(maxsplit=1)
        when_token = parts[0]
        note = parts[1].strip() if len(parts) > 1 else ""
        delta = parse_duration(when_token)
        if delta is None:
            await edit_or_reply(
                event,
                "Could not parse time. Use forms like `10m`, `2h`, `1d`, `1h30m`.",
            )
            return

        chat = await event.get_chat()
        link = message_permalink(chat, event.chat_id, reply.id)
        snippet = (reply.message or "[media]").replace("\n", " ")
        if len(snippet) > 80:
            snippet = snippet[:77] + "..."
        text = f"Later: {snippet}\n{link}"
        if note:
            text = f"{note}\n\n{text}"

        due = utc_now() + delta
        # Deliver reminder to Saved Messages so it always reaches you
        me = await client.get_me()
        rid = await db.add_reminder(
            due_at=to_iso(due),
            text=text,
            chat_id=me.id,
            created_at=to_iso(utc_now()),
        )
        await edit_or_reply(
            event,
            f"Later `#{rid}` at **{format_local(due)}**\n{link}",
        )
