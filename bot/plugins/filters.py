"""DM keyword auto-replies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from telethon import events

from bot.utils.decorators import command, edit_or_reply, register_help
from bot.utils.timeparse import to_iso, utc_now

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database

_last_hit: dict[tuple[int, str], float] = {}
_COOLDOWN_SEC = 45


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    p = config.cmd_prefix
    register_help(
        client,
        "Filters",
        [
            f"{p}filter add <keyword> <reply> — DM auto-reply",
            f"{p}filter list — list filters",
            f"{p}filter del <keyword> — delete filter",
        ],
    )

    @command(client, config, r"filter(?:\s+(.*))?$")
    async def filter_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        if not raw:
            await edit_or_reply(
                event,
                f"Usage:\n`{p}filter add keyword reply text`\n"
                f"`{p}filter list`\n`{p}filter del keyword`",
            )
            return

        parts = raw.split(maxsplit=2)
        action = parts[0].lower()

        if action == "list":
            rows = await db.list_filters()
            if not rows:
                await edit_or_reply(event, "No filters.")
                return
            lines = ["**Filters** (DM only)"]
            for r in rows:
                lines.append(f"• `{r['keyword']}` → {r['response'][:80]}")
            await edit_or_reply(event, "\n".join(lines))
            return

        if action == "add":
            if len(parts) < 3:
                await edit_or_reply(event, f"Usage: `{p}filter add <keyword> <reply>`")
                return
            keyword, response = parts[1].lower(), parts[2]
            await db.upsert_filter(keyword, response, to_iso(utc_now()))
            await edit_or_reply(event, f"Filter `{keyword}` saved.")
            return

        if action in {"del", "delete", "rm"}:
            if len(parts) < 2:
                await edit_or_reply(event, f"Usage: `{p}filter del <keyword>`")
                return
            keyword = parts[1].lower()
            ok = await db.delete_filter(keyword)
            await edit_or_reply(
                event,
                f"Deleted `{keyword}`." if ok else f"No filter `{keyword}`.",
            )
            return

        await edit_or_reply(event, f"Unknown action. Try `{p}help`.")

    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def filter_watcher(event) -> None:
        text = (event.raw_text or "").strip()
        if not text:
            return
        sender = await event.get_sender()
        if sender is None or getattr(sender, "bot", False) or getattr(sender, "is_self", False):
            return

        matches = await db.match_filters(text)
        if not matches:
            return

        now = utc_now().timestamp()
        for row in matches:
            key = (event.sender_id or 0, row["keyword"].lower())
            if now - _last_hit.get(key, 0) < _COOLDOWN_SEC:
                continue
            _last_hit[key] = now
            await event.reply(row["response"])
            break  # one reply per message
