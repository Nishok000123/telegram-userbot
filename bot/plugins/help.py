"""Help command — lists registered plugin help."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot.utils.decorators import command, edit_or_reply, register_help

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    register_help(
        client,
        "Basics",
        [
            f"{config.cmd_prefix}help — show this list",
            f"{config.cmd_prefix}ping — response time",
            f"{config.cmd_prefix}alive — status",
            f"{config.cmd_prefix}id — chat / user / channel IDs",
        ],
    )

    @command(client, config, r"help$")
    async def help_cmd(event) -> None:
        sections = getattr(client, "_userbot_help", [])
        lines = ["**Personal Userbot — Commands**", ""]
        for section, items in sections:
            lines.append(f"**{section}**")
            lines.extend(f"• {item}" for item in items)
            lines.append("")
        lines.append("_Type commands in any chat, including Saved Messages._")
        await edit_or_reply(event, "\n".join(lines).strip())
