"""Reminders with a background poller."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from bot.utils.decorators import command, edit_or_reply, register_help
from bot.utils.timeparse import (
    format_local,
    from_iso,
    parse_duration,
    to_iso,
    utc_now,
)

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    p = config.cmd_prefix
    register_help(
        client,
        "Reminders",
        [
            f"{p}remind <when> <text> — e.g. `{p}remind 30m call mom`",
            f"{p}remind list — pending reminders",
            f"{p}remind del <id> — cancel a reminder",
        ],
    )

    @command(client, config, r"remind(?:\s+(.*))?$")
    async def remind_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        if not raw:
            await edit_or_reply(
                event,
                f"Usage:\n`{p}remind 30m text`\n`{p}remind 2h text`\n"
                f"`{p}remind list`\n`{p}remind del <id>`",
            )
            return

        parts = raw.split(maxsplit=1)
        action = parts[0].lower()

        if action == "list":
            rows = await db.list_reminders()
            if not rows:
                await edit_or_reply(event, "No pending reminders.")
                return
            lines = ["**Reminders**"]
            for r in rows:
                due = format_local(from_iso(r["due_at"]))
                lines.append(f"• `#{r['id']}` {due} — {r['text']}")
            await edit_or_reply(event, "\n".join(lines))
            return

        if action in {"del", "delete", "rm"}:
            if len(parts) < 2 or not parts[1].strip().isdigit():
                await edit_or_reply(event, f"Usage: `{p}remind del <id>`")
                return
            rid = int(parts[1].strip())
            ok = await db.delete_reminder(rid)
            await edit_or_reply(
                event,
                f"Deleted reminder `#{rid}`." if ok else f"No reminder `#{rid}`.",
            )
            return

        # Create: first token is duration
        when_token = parts[0]
        text = parts[1].strip() if len(parts) > 1 else ""
        if not text:
            await edit_or_reply(event, f"Usage: `{p}remind 30m your text here`")
            return

        delta = parse_duration(when_token)
        if delta is None:
            await edit_or_reply(
                event,
                "Could not parse time. Use forms like `10m`, `2h`, `1d`, `1h30m`.",
            )
            return

        due = utc_now() + delta
        rid = await db.add_reminder(
            due_at=to_iso(due),
            text=text,
            chat_id=event.chat_id,
            created_at=to_iso(utc_now()),
        )
        await edit_or_reply(
            event,
            f"Reminder `#{rid}` set for **{format_local(due)}**\n{text}",
        )

    async def reminder_loop() -> None:
        await asyncio.sleep(3)
        while True:
            try:
                due = await db.due_reminders(to_iso(utc_now()))
                for row in due:
                    try:
                        await client.send_message(
                            row["chat_id"],
                            f"**Reminder `#{row['id']}`**\n{row['text']}",
                        )
                    except Exception as exc:  # noqa: BLE001
                        print(f"Reminder send failed #{row['id']}: {exc}")
                    await db.mark_reminder_done(row["id"])
            except Exception as exc:  # noqa: BLE001
                print(f"Reminder loop error: {exc}")
            await asyncio.sleep(20)

    client._userbot_bg_tasks.append(reminder_loop)  # type: ignore[attr-defined]
