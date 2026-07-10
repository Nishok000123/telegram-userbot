"""Lock users — auto-archive their DM / chats on incoming message."""

from __future__ import annotations

from typing import TYPE_CHECKING

from telethon import events

from bot.utils.decorators import command, edit_or_reply, register_help
from bot.utils.peers import display_user, resolve_user
from bot.utils.timeparse import to_iso, utc_now

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    p = config.cmd_prefix
    register_help(
        client,
        "Lock",
        [
            f"{p}lock [reason] — lock user (reply/@user); auto-archive their DM",
            f"{p}unlock — unlock user",
            f"{p}lock list — show locked users",
        ],
    )

    @command(client, config, r"lock(?:\s+(.*))?$")
    async def lock_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        if raw.lower() == "list" or raw.lower().startswith("list "):
            rows = await db.list_locks()
            if not rows:
                await edit_or_reply(event, "No locked users.")
                return
            lines = ["**Locked**"]
            for r in rows:
                uname = f" @{r['username']}" if r.get("username") else ""
                reason = f" — {r['reason']}" if r.get("reason") else ""
                lines.append(
                    f"• {r.get('display_name') or 'Unknown'}{uname} "
                    f"(`{r['user_id']}`){reason}"
                )
            await edit_or_reply(event, "\n".join(lines))
            return

        tokens = raw.split() if raw else []
        # If first token looks like @user/id, resolve peels it; else all is reason
        user, leftover, err = await resolve_user(client, event, tokens)
        if err or user is None:
            await edit_or_reply(event, err or "No user.")
            return
        reason = " ".join(leftover) or None
        await db.upsert_lock(
            user_id=user.id,
            display_name=display_user(user),
            username=user.username,
            reason=reason,
            created_at=to_iso(utc_now()),
        )
        # Also tag as spam for discoverability
        await db.upsert_tag(
            user_id=user.id,
            label="spam",
            note=reason,
            display_name=display_user(user),
            username=user.username,
            updated_at=to_iso(utc_now()),
        )
        try:
            await client.edit_folder(user.id, folder=1)
        except Exception:
            pass
        extra = f" — {reason}" if reason else ""
        await edit_or_reply(event, f"Locked **{display_user(user)}**{extra}.")

    @command(client, config, r"unlock(?:\s+(.*))?$")
    async def unlock_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        tokens = raw.split() if raw else []
        user, _, err = await resolve_user(client, event, tokens)
        if err or user is None:
            await edit_or_reply(event, err or "No user.")
            return
        ok = await db.delete_lock(user.id)
        try:
            await client.edit_folder(user.id, folder=0)
        except Exception:
            pass
        await edit_or_reply(
            event,
            f"Unlocked **{display_user(user)}**."
            if ok
            else f"**{display_user(user)}** was not locked.",
        )

    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def lock_watcher(event) -> None:
        sender_id = event.sender_id
        if not sender_id:
            return
        if not await db.is_locked(sender_id):
            return
        try:
            await client.edit_folder(sender_id, folder=1)
        except Exception:
            pass
