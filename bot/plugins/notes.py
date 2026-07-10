"""Named notes stored in SQLite."""

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
        "Notes",
        [
            f"{p}note add <name> <text> — save a note",
            f"{p}note get <name> — show a note",
            f"{p}note list — list note names",
            f"{p}note del <name> — delete a note",
        ],
    )

    @command(client, config, r"note(?:\s+(.*))?$")
    async def note_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        if not raw:
            await edit_or_reply(
                event,
                f"Usage:\n`{p}note add name text`\n`{p}note get name`\n"
                f"`{p}note list`\n`{p}note del name`",
            )
            return

        parts = raw.split(maxsplit=2)
        action = parts[0].lower()

        if action == "list":
            names = await db.list_notes()
            if not names:
                await edit_or_reply(event, "No notes yet.")
                return
            body = "\n".join(f"• `{n}`" for n in names)
            await edit_or_reply(event, f"**Notes**\n{body}")
            return

        if action == "add":
            if len(parts) < 3:
                await edit_or_reply(event, f"Usage: `{p}note add <name> <text>`")
                return
            name, content = parts[1], parts[2]
            await db.upsert_note(name, content, to_iso(utc_now()))
            await edit_or_reply(event, f"Saved note `{name}`.")
            return

        if action == "get":
            if len(parts) < 2:
                await edit_or_reply(event, f"Usage: `{p}note get <name>`")
                return
            name = parts[1]
            content = await db.get_note(name)
            if content is None:
                await edit_or_reply(event, f"No note named `{name}`.")
                return
            await edit_or_reply(event, f"**Note `{name}`**\n{content}")
            return

        if action in {"del", "delete", "rm"}:
            if len(parts) < 2:
                await edit_or_reply(event, f"Usage: `{p}note del <name>`")
                return
            name = parts[1]
            ok = await db.delete_note(name)
            await edit_or_reply(
                event, f"Deleted `{name}`." if ok else f"No note named `{name}`."
            )
            return

        await edit_or_reply(event, f"Unknown action. Try `{p}help`.")
