"""Inactive chat organizer — suggest archive/leave, never auto-leave."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from telethon import events
from telethon.tl.types import Channel, Chat, User

from bot.utils.decorators import command, edit_or_reply, register_help
from bot.utils.timeparse import format_local, from_iso, to_iso, utc_now

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database

_NUDGE_SETTING = "org_last_nudge"


def _kind_of(entity: Any) -> str:
    if isinstance(entity, User):
        return "user"
    if isinstance(entity, Channel):
        if entity.broadcast:
            return "channel"
        return "supergroup"
    if isinstance(entity, Chat):
        return "group"
    return "other"


def _title_of(entity: Any, dialog: Any = None) -> str:
    if dialog and getattr(dialog, "name", None):
        return dialog.name
    return (
        getattr(entity, "title", None)
        or " ".join(
            p
            for p in [getattr(entity, "first_name", None), getattr(entity, "last_name", None)]
            if p
        )
        or str(getattr(entity, "id", "?"))
    )


async def refresh_activity_from_dialogs(
    client: "TelegramClient", db: "Database", *, limit: int = 200
) -> int:
    count = 0
    async for dialog in client.iter_dialogs(limit=limit):
        entity = dialog.entity
        kind = _kind_of(entity)
        if kind == "user":
            continue  # focus channels/groups for clean suggestions
        chat_id = dialog.id
        title = _title_of(entity, dialog)
        seen = None
        if dialog.date:
            seen = to_iso(dialog.date) if hasattr(dialog.date, "tzinfo") else str(dialog.date)
            # normalize via utc if datetime
            try:
                from datetime import datetime, timezone

                if isinstance(dialog.date, datetime):
                    dt = dialog.date
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    seen = to_iso(dt)
            except Exception:
                pass
        await db.upsert_chat_activity(
            chat_id=chat_id,
            title=title,
            kind=kind,
            last_seen_at=seen,
        )
        count += 1
    return count


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    p = config.cmd_prefix
    days_default = config.org_inactive_days
    register_help(
        client,
        "Organizer",
        [
            f"{p}org scan — refresh activity from dialogs",
            f"{p}org inactive [days] — list quiet channels/groups",
            f"{p}org clean — suggest archive/leave (confirm yourself)",
            f"{p}org archive <@|id> — archive chat",
            f"{p}org leave <@|id> — leave chat (explicit)",
        ],
    )

    @client.on(events.NewMessage(incoming=True))
    async def activity_incoming(event) -> None:
        if event.is_private:
            return
        try:
            chat = await event.get_chat()
            await db.upsert_chat_activity(
                chat_id=event.chat_id,
                title=_title_of(chat),
                kind=_kind_of(chat),
                last_seen_at=to_iso(utc_now()),
                last_open_at=to_iso(utc_now()),
            )
        except Exception:
            pass

    @client.on(events.NewMessage(outgoing=True))
    async def activity_outgoing(event) -> None:
        if event.is_private:
            return
        try:
            chat = await event.get_chat()
            await db.upsert_chat_activity(
                chat_id=event.chat_id,
                title=_title_of(chat),
                kind=_kind_of(chat),
                last_seen_at=to_iso(utc_now()),
                last_open_at=to_iso(utc_now()),
            )
        except Exception:
            pass

    async def _inactive_rows(days: int) -> list[dict[str, Any]]:
        before = utc_now() - timedelta(days=days)
        return await db.list_inactive_chats(to_iso(before), limit=40)

    @command(client, config, r"org(?:\s+(.*))?$")
    async def org_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        if not raw:
            await edit_or_reply(
                event,
                f"Usage:\n`{p}org scan`\n`{p}org inactive [days]`\n"
                f"`{p}org clean`\n`{p}org archive <id|@>`\n"
                f"`{p}org leave <id|@>`",
            )
            return

        parts = raw.split(maxsplit=1)
        action = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        if action == "scan":
            await edit_or_reply(event, "Scanning dialogs…")
            n = await refresh_activity_from_dialogs(client, db)
            await edit_or_reply(event, f"Updated activity for **{n}** chats.")
            return

        if action == "inactive":
            days = days_default
            if rest.isdigit():
                days = max(1, int(rest))
            rows = await _inactive_rows(days)
            if not rows:
                await edit_or_reply(
                    event,
                    f"No inactive chats (>{days}d). Try `{p}org scan` first.",
                )
                return
            lines = [f"**Inactive** (>{days} days)"]
            for r in rows[:25]:
                when = r.get("last_open_at") or r.get("last_seen_at") or "?"
                try:
                    when = format_local(from_iso(when))
                except Exception:
                    pass
                lines.append(
                    f"• `{r['chat_id']}` {r.get('title') or '?'} "
                    f"[{r.get('kind')}] — {when}"
                )
            await edit_or_reply(event, "\n".join(lines))
            return

        if action == "clean":
            await refresh_activity_from_dialogs(client, db)
            rows = await _inactive_rows(days_default)
            if not rows:
                await edit_or_reply(event, "Nothing to clean. All active enough.")
                return
            lines = [
                f"**Clean suggest** (>{days_default}d, confirm yourself)",
                "_Never auto-leaves. You pick._",
                "",
                "**Archive candidates**",
            ]
            for r in rows[:10]:
                lines.append(
                    f"• `{p}org archive {r['chat_id']}` — {r.get('title')}"
                )
            lines.append("")
            lines.append("**Leave candidates** (most inactive first)")
            for r in rows[:10]:
                if r.get("kind") in {"channel", "supergroup", "group"}:
                    lines.append(
                        f"• `{p}org leave {r['chat_id']}` — {r.get('title')}"
                    )
            await edit_or_reply(event, "\n".join(lines))
            return

        if action == "archive":
            if not rest:
                await edit_or_reply(event, f"Usage: `{p}org archive <id|@>`")
                return
            try:
                entity = await client.get_entity(rest)
                await client.edit_folder(entity, folder=1)
                await edit_or_reply(event, f"Archived `{rest}`.")
            except Exception as exc:  # noqa: BLE001
                await edit_or_reply(event, f"Archive failed: `{exc}`")
            return

        if action == "leave":
            if not rest:
                await edit_or_reply(
                    event,
                    f"Usage: `{p}org leave <id|@>` "
                    f"(explicit confirm — no mass leave)",
                )
                return
            try:
                entity = await client.get_entity(rest)
                await client.delete_dialog(entity)
                try:
                    cid = await client.get_peer_id(entity)
                    await db.delete_chat_activity(cid)
                except Exception:
                    pass
                await edit_or_reply(event, f"Left / deleted dialog `{rest}`.")
            except Exception as exc:  # noqa: BLE001
                await edit_or_reply(event, f"Leave failed: `{exc}`")
            return

        await edit_or_reply(event, f"Unknown action. Try `{p}help`.")

    async def org_nudge_loop() -> None:
        await asyncio.sleep(120)
        while True:
            try:
                last = await db.get_setting(_NUDGE_SETTING)
                now = utc_now()
                should = True
                if last:
                    try:
                        prev = from_iso(last)
                        should = (now - prev) >= timedelta(days=7)
                    except Exception:
                        should = True
                if should:
                    rows = await _inactive_rows(days_default)
                    if len(rows) >= 5:
                        me = await client.get_me()
                        await client.send_message(
                            me.id,
                            f"**Organizer nudge**\n"
                            f"{len(rows)} chats inactive >{days_default}d.\n"
                            f"Review: `{p}org clean`",
                        )
                        await db.set_setting(_NUDGE_SETTING, to_iso(now))
            except Exception as exc:  # noqa: BLE001
                print(f"Org nudge error: {exc}")
            await asyncio.sleep(6 * 3600)

    client._userbot_bg_tasks.append(org_nudge_loop)  # type: ignore[attr-defined]
