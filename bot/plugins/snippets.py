"""Quick reply snippets."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot.utils.decorators import command, edit_or_reply, register_help
from bot.utils.timeparse import to_iso, utc_now

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    p = config.cmd_prefix
    register_help(
        client,
        "Snippets",
        [
            f"{p}snip add <name> <text> — save a snippet",
            f"{p}snip get <name> — paste a snippet",
            f"{p}snip list — list snippets",
            f"{p}snip del <name> — delete a snippet",
        ],
    )

    @command(client, config, r"snip(?:\s+(.*))?$")
    async def snip_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        if not raw:
            await edit_or_reply(
                event,
                f"Usage:\n`{p}snip add name text`\n`{p}snip get name`\n"
                f"`{p}snip list`\n`{p}snip del name`",
            )
            return

        parts = raw.split(maxsplit=2)
        action = parts[0].lower()

        if action == "list":
            names = await db.list_snippets()
            if not names:
                await edit_or_reply(event, "No snippets yet.")
                return
            body = "\n".join(f"• `{n}`" for n in names)
            await edit_or_reply(event, f"**Snippets**\n{body}")
            return

        if action == "add":
            if len(parts) < 3:
                await edit_or_reply(event, f"Usage: `{p}snip add <name> <text>`")
                return
            name, content = parts[1], parts[2]
            await db.upsert_snippet(name, content, to_iso(utc_now()))
            await edit_or_reply(event, f"Saved snippet `{name}`.")
            return

        if action == "get":
            if len(parts) < 2:
                await edit_or_reply(event, f"Usage: `{p}snip get <name>`")
                return
            name = parts[1]
            content = await db.get_snippet(name)
            if content is None:
                await edit_or_reply(event, f"No snippet named `{name}`.")
                return
            # Replace the command with the snippet text (ready to send / copy)
            await edit_or_reply(event, content)
            return

        if action in {"del", "delete", "rm"}:
            if len(parts) < 2:
                await edit_or_reply(event, f"Usage: `{p}snip del <name>`")
                return
            name = parts[1]
            ok = await db.delete_snippet(name)
            await edit_or_reply(
                event,
                f"Deleted `{name}`." if ok else f"No snippet named `{name}`.",
            )
            return

        await edit_or_reply(event, f"Unknown action. Try `{p}help`.")
