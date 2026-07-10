"""Personal tags — label Telegram users and find them later."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bot.utils.decorators import command, edit_or_reply, register_help
from bot.utils.peers import display_user, resolve_user
from bot.utils.timeparse import to_iso, utc_now

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database


def _format_person(row: dict[str, Any]) -> str:
    name = row.get("display_name") or "Unknown"
    uname = f" @{row['username']}" if row.get("username") else ""
    note = f" — {row['note']}" if row.get("note") else ""
    return f"• {name}{uname} (`{row['user_id']}`) [{row['label']}]{note}"


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    p = config.cmd_prefix
    register_help(
        client,
        "Tags",
        [
            f"{p}tag add <label> [note] — tag user (reply / @user / DM)",
            f"{p}tag get — show tags for user",
            f"{p}tag list — all tags",
            f"{p}tag list <label> — people with that label",
            f"{p}tag del <label> — remove one label from user",
            f"{p}tag clear — remove all labels from user",
            f"{p}who — reply → name + your tags",
        ],
    )

    @command(client, config, r"tag(?:\s+(.*))?$")
    async def tag_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        if not raw:
            await edit_or_reply(
                event,
                f"Usage:\n"
                f"`{p}tag add label [note]` (reply/@user)\n"
                f"`{p}tag get` (reply/@user)\n"
                f"`{p}tag list` / `{p}tag list label`\n"
                f"`{p}tag del label`\n"
                f"`{p}tag clear`",
            )
            return

        parts = raw.split()
        action = parts[0].lower()
        rest = parts[1:]

        if action == "list":
            if rest:
                label = rest[0].lower()
                rows = await db.list_users_by_label(label)
                if not rows:
                    await edit_or_reply(event, f"No one tagged `{label}`.")
                    return
                body = "\n".join(_format_person(r) for r in rows)
                await edit_or_reply(event, f"**Tag `{label}`** ({len(rows)})\n{body}")
                return

            rows = await db.list_all_tags()
            if not rows:
                await edit_or_reply(event, "No tags yet.")
                return
            body = "\n".join(_format_person(r) for r in rows)
            await edit_or_reply(event, f"**All tags** ({len(rows)})\n{body}")
            return

        if action == "add":
            user, leftover, err = await resolve_user(client, event, rest)
            if err or user is None:
                await edit_or_reply(event, err or "No user.")
                return
            if not leftover:
                await edit_or_reply(
                    event,
                    f"Usage: `{p}tag add <label> [note]` (reply or `@user` first)",
                )
                return
            label = leftover[0].lower()
            note = " ".join(leftover[1:]) or None
            await db.upsert_tag(
                user_id=user.id,
                label=label,
                note=note,
                display_name=display_user(user),
                username=user.username,
                updated_at=to_iso(utc_now()),
            )
            extra = f" — {note}" if note else ""
            await edit_or_reply(
                event,
                f"Tagged **{display_user(user)}** as `{label}`{extra}.",
            )
            return

        if action == "get":
            user, _, err = await resolve_user(client, event, rest)
            if err or user is None:
                await edit_or_reply(event, err or "No user.")
                return
            rows = await db.get_tags_for_user(user.id)
            uname = f" @{user.username}" if user.username else ""
            header = f"**{display_user(user)}**{uname} (`{user.id}`)"
            if not rows:
                await edit_or_reply(event, f"{header}\nNo tags.")
                return
            lines = [header]
            for r in rows:
                note = f" — {r['note']}" if r.get("note") else ""
                lines.append(f"• `{r['label']}`{note}")
            await edit_or_reply(event, "\n".join(lines))
            return

        if action in {"del", "delete", "rm"}:
            user, leftover, err = await resolve_user(client, event, rest)
            if err or user is None:
                await edit_or_reply(event, err or "No user.")
                return
            if not leftover:
                await edit_or_reply(event, f"Usage: `{p}tag del <label>`")
                return
            label = leftover[0].lower()
            ok = await db.delete_tag(user.id, label)
            await edit_or_reply(
                event,
                f"Removed `{label}` from **{display_user(user)}**."
                if ok
                else f"**{display_user(user)}** has no tag `{label}`.",
            )
            return

        if action == "clear":
            user, _, err = await resolve_user(client, event, rest)
            if err or user is None:
                await edit_or_reply(event, err or "No user.")
                return
            n = await db.clear_tags(user.id)
            await edit_or_reply(
                event,
                f"Cleared {n} tag(s) from **{display_user(user)}**."
                if n
                else f"**{display_user(user)}** had no tags.",
            )
            return

        await edit_or_reply(event, f"Unknown action. Try `{p}help`.")

    @command(client, config, r"who(?:\s+(.*))?$")
    async def who_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        tokens = raw.split() if raw else []
        user, _, err = await resolve_user(client, event, tokens)
        if err or user is None:
            await edit_or_reply(event, err or "No user.")
            return

        rows = await db.get_tags_for_user(user.id)
        uname = f"@{user.username}" if user.username else "(no username)"
        lines = [
            f"**{display_user(user)}**",
            f"• Username: {uname}",
            f"• ID: `{user.id}`",
        ]
        if rows:
            lines.append("• Tags:")
            for r in rows:
                note = f" — {r['note']}" if r.get("note") else ""
                lines.append(f"  `{r['label']}`{note}")
        else:
            lines.append("• Tags: _(none)_")
        await edit_or_reply(event, "\n".join(lines))
