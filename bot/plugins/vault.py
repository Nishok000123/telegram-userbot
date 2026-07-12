"""Vault channel + Premium-like message tags."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telethon.tl.functions.channels import CreateChannelRequest

from bot.utils.decorators import command, edit_or_reply, register_help
from bot.utils.peers import get_reply_or_fail, message_permalink
from bot.utils.timeparse import to_iso, utc_now

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database

VAULT_SETTING = "vault_chat_id"
VAULT_TITLE = "UB Vault"


async def _get_vault_id(db: "Database") -> int | None:
    raw = await db.get_setting(VAULT_SETTING)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _preview_text(msg: Any, limit: int = 100) -> str:
    text = (getattr(msg, "message", None) or "").replace("\n", " ").strip()
    if text:
        return text[:limit] + ("…" if len(text) > limit else "")
    if getattr(msg, "media", None):
        return "[media]"
    return "[empty]"


def _topic_id_from_msg(msg: Any) -> int | None:
    reply_to = getattr(msg, "reply_to", None)
    if reply_to is None:
        return None
    if getattr(reply_to, "forum_topic", False):
        return getattr(reply_to, "reply_to_msg_id", None)
    return None


async def _copy_to_vault(
    client: "TelegramClient",
    vault_id: int,
    src_msg: Any,
    caption_extra: str,
    downloads_dir,
) -> int:
    """Copy message into vault; return vault message id."""
    try:
        sent = await client.forward_messages(vault_id, src_msg)
        # forward_messages may return list
        if isinstance(sent, list):
            sent = sent[0]
        if caption_extra:
            await client.send_message(vault_id, caption_extra, reply_to=sent.id)
        return int(sent.id)
    except Exception:
        pass

    body = caption_extra
    if src_msg.message:
        body = f"{src_msg.message}\n\n{caption_extra}" if caption_extra else src_msg.message

    if src_msg.media:
        path = await src_msg.download_media(file=str(downloads_dir / "vault_"))
        if path:
            sent = await client.send_file(vault_id, path, caption=body or None)
            try:
                from pathlib import Path

                Path(path).unlink(missing_ok=True)
            except OSError:
                pass
            return int(sent.id)

    sent = await client.send_message(vault_id, body or "(empty)")
    return int(sent.id)


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    p = config.cmd_prefix
    register_help(
        client,
        "Vault / msg tags",
        [
            f"{p}vault setup — create/find private UB Vault channel",
            f"{p}mtag <tag> [note] — reply → save to vault with #tag",
            f"{p}msave <tag> [note] — same as mtag",
            f"{p}msearch <tag> — list tagged msgs (Premium-like)",
            f"{p}mtags — tag counts",
            f"{p}mtag del <id> — remove index (+ try delete vault msg)",
        ],
    )

    @command(client, config, r"vault(?:\s+(.*))?$")
    async def vault_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip().lower()
        if raw not in {"setup", "status", ""}:
            await edit_or_reply(
                event,
                f"Usage:\n`{p}vault setup`\n`{p}vault status`",
            )
            return

        if raw in {"", "status"}:
            vid = await _get_vault_id(db)
            if not vid:
                await edit_or_reply(
                    event, f"No vault yet. Run `{p}vault setup`."
                )
                return
            await edit_or_reply(event, f"Vault chat id: `{vid}`")
            return

        # setup
        existing = await _get_vault_id(db)
        if existing:
            try:
                await client.get_entity(existing)
                await edit_or_reply(event, f"Vault already set: `{existing}`")
                return
            except Exception:
                pass

        # Try find existing channel by title among dialogs
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if (
                getattr(entity, "broadcast", False)
                and (getattr(entity, "title", None) or "") == VAULT_TITLE
            ):
                await db.set_setting(VAULT_SETTING, str(dialog.id))
                await edit_or_reply(
                    event, f"Found existing **{VAULT_TITLE}** → `{dialog.id}`"
                )
                return

        try:
            result = await client(
                CreateChannelRequest(
                    title=VAULT_TITLE,
                    about="Personal tagged message vault (userbot)",
                    megagroup=False,
                )
            )
            channel = result.chats[0]
            from telethon import utils as tg_utils

            vault_id = tg_utils.get_peer_id(channel)
            await db.set_setting(VAULT_SETTING, str(vault_id))
            await edit_or_reply(
                event,
                f"**{VAULT_TITLE}** ready.\nChat id: `{vault_id}`\n"
                f"Use `{p}mtag study` (reply to a msg).",
            )
        except Exception as exc:  # noqa: BLE001
            await edit_or_reply(
                event,
                f"Vault create failed: `{exc}`\n"
                f"Channel limit? Run `{p}org clean` then leave inactive, "
                f"retry `{p}vault setup`.",
            )

    async def _mtag_core(event, raw: str) -> None:
        parts = raw.split(maxsplit=1)
        if not parts:
            await edit_or_reply(
                event, f"Usage: `{p}mtag <tag> [note]` (reply to a message)"
            )
            return

        if parts[0].lower() in {"del", "delete", "rm"}:
            if len(parts) < 2 or not parts[1].strip().isdigit():
                await edit_or_reply(event, f"Usage: `{p}mtag del <id>`")
                return
            tag_id = int(parts[1].strip())
            row = await db.delete_msg_tag(tag_id)
            if not row:
                await edit_or_reply(event, f"No msg tag `#{tag_id}`.")
                return
            try:
                await client.delete_messages(row["vault_chat_id"], [row["vault_msg_id"]])
            except Exception:
                pass
            await edit_or_reply(event, f"Deleted msg tag `#{tag_id}`.")
            return

        tag = parts[0].lower().lstrip("#")
        note = parts[1].strip() if len(parts) > 1 else None
        if not tag:
            await edit_or_reply(event, "Tag name required.")
            return

        vault_id = await _get_vault_id(db)
        if not vault_id:
            await edit_or_reply(event, f"No vault. Run `{p}vault setup` first.")
            return

        reply, err = await get_reply_or_fail(event)
        if err or reply is None:
            await edit_or_reply(event, err or "No reply.")
            return

        src_chat = await event.get_chat()
        src_link = message_permalink(src_chat, event.chat_id, reply.id)
        caption = f"#{tag}"
        if note:
            caption += f"\n{note}"
        caption += f"\nSource: {src_link}"

        try:
            vault_msg_id = await _copy_to_vault(
                client, vault_id, reply, caption, config.downloads_dir
            )
        except Exception as exc:  # noqa: BLE001
            await edit_or_reply(event, f"Save to vault failed: `{exc}`")
            return

        topic_id = _topic_id_from_msg(reply)
        rid = await db.add_msg_tag(
            tag=tag,
            vault_msg_id=vault_msg_id,
            vault_chat_id=vault_id,
            source_chat_id=event.chat_id,
            source_msg_id=reply.id,
            topic_id=topic_id,
            note=note,
            preview=_preview_text(reply),
            created_at=to_iso(utc_now()),
        )
        vault_link = message_permalink(None, vault_id, vault_msg_id)
        # message_permalink with None chat still works for -100 ids
        await edit_or_reply(
            event,
            f"Tagged `#{tag}` as `#{rid}`\nVault: {vault_link}",
        )

    @command(client, config, r"mtag(?:\s+(.*))?$")
    async def mtag_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        if not raw:
            await edit_or_reply(
                event,
                f"Usage:\n`{p}mtag study [note]` (reply)\n"
                f"`{p}mtag del <id>`\n`{p}msearch study`",
            )
            return
        await _mtag_core(event, raw)

    @command(client, config, r"msave(?:\s+(.*))?$")
    async def msave_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        if not raw:
            await edit_or_reply(event, f"Usage: `{p}msave study [note]` (reply)")
            return
        await _mtag_core(event, raw)

    @command(client, config, r"msearch(?:\s+(\S+))?$")
    async def msearch_cmd(event) -> None:
        tag = (event.pattern_match.group(1) or "").strip().lstrip("#").lower()
        if not tag:
            await edit_or_reply(event, f"Usage: `{p}msearch study`")
            return
        rows = await db.search_msg_tags(tag)
        if not rows:
            await edit_or_reply(event, f"No messages tagged `#{tag}`.")
            return
        lines = [f"**#{tag}** ({len(rows)})"]
        for r in rows:
            preview = r.get("preview") or "[…]"
            note = f" — {r['note']}" if r.get("note") else ""
            vlink = message_permalink(None, r["vault_chat_id"], r["vault_msg_id"])
            lines.append(f"• `#{r['id']}` {preview}{note}\n  {vlink}")
        await edit_or_reply(event, "\n".join(lines))

    @command(client, config, r"mtags$")
    async def mtags_cmd(event) -> None:
        rows = await db.list_msg_tag_counts()
        if not rows:
            await edit_or_reply(event, "No message tags yet.")
            return
        lines = ["**Message tags**"]
        for r in rows:
            lines.append(f"• `#{r['tag']}` — {r['cnt']}")
        await edit_or_reply(event, "\n".join(lines))
