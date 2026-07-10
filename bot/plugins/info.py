"""Show chat / user / channel IDs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from telethon.tl.types import Channel, Chat, User

from bot.utils.decorators import command, edit_or_reply

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    @command(client, config, r"id$")
    async def id_cmd(event) -> None:
        chat = await event.get_chat()
        lines = ["**IDs**", f"• Chat ID: `{event.chat_id}`"]

        if isinstance(chat, User):
            lines.append(f"• User: {chat.first_name or ''} (`{chat.id}`)")
            if chat.username:
                lines.append(f"• Username: @{chat.username}")
        elif isinstance(chat, Channel):
            kind = "Channel" if chat.broadcast else "Supergroup"
            lines.append(f"• {kind}: {chat.title} (`{chat.id}`)")
            if chat.username:
                lines.append(f"• Username: @{chat.username}")
        elif isinstance(chat, Chat):
            lines.append(f"• Group: {chat.title} (`{chat.id}`)")

        if event.is_reply:
            reply = await event.get_reply_message()
            sender = await reply.get_sender()
            if isinstance(sender, User):
                lines.append(
                    f"• Replied user: {sender.first_name or ''} (`{sender.id}`)"
                )
                if sender.username:
                    lines.append(f"• Replied username: @{sender.username}")
            elif isinstance(sender, Channel):
                lines.append(f"• Replied channel: {sender.title} (`{sender.id}`)")
            lines.append(f"• Replied message ID: `{reply.id}`")

        me = await client.get_me()
        lines.append(f"• Your ID: `{me.id}`")
        await edit_or_reply(event, "\n".join(lines))
