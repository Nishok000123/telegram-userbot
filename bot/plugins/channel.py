"""Channel management commands (no group moderation)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import Channel, MessageMediaDocument, MessageMediaPhoto

from bot.utils.decorators import command, edit_or_reply, register_help
from bot.utils.timeparse import format_local, parse_duration, utc_now

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database

DEFAULT_CHANNEL_KEY = "default_channel"


def _clean_channel_ref(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"^https?://t\.me/", "", text, flags=re.IGNORECASE)
    text = text.lstrip("@")
    return text.strip()


async def _resolve_channel(client: "TelegramClient", ref: str) -> Any:
    cleaned = _clean_channel_ref(ref)
    if cleaned.lstrip("-").isdigit():
        entity = await client.get_entity(int(cleaned))
    else:
        entity = await client.get_entity(cleaned)
    if not isinstance(entity, Channel) or not entity.broadcast:
        raise ValueError("That is not a channel.")
    return entity


async def _get_default_channel(
    client: "TelegramClient", db: "Database"
) -> Any | None:
    ref = await db.get_setting(DEFAULT_CHANNEL_KEY)
    if not ref:
        return None
    return await _resolve_channel(client, ref)


async def _pick_channel(
    client: "TelegramClient",
    db: "Database",
    config: "Config",
    maybe_channel: str | None,
    rest: str,
) -> tuple[Any, str]:
    """Return (channel_entity, remaining_text).

    If maybe_channel looks like a channel ref, use it; else use default channel
    and treat maybe_channel as part of the text.
    """
    p = config.cmd_prefix
    if maybe_channel:
        try:
            entity = await _resolve_channel(client, maybe_channel)
            return entity, rest
        except Exception:
            # Not a channel — fall back to default and rebuild text
            rebuilt = f"{maybe_channel} {rest}".strip() if rest else maybe_channel
            entity = await _get_default_channel(client, db)
            if entity is None:
                raise ValueError(
                    f"No channel given and no default set. "
                    f"Use `{p}cset @channel` or pass a channel."
                )
            return entity, rebuilt

    entity = await _get_default_channel(client, db)
    if entity is None:
        raise ValueError(
            f"No channel given and no default set. "
            f"Use `{p}cset @channel` or pass a channel."
        )
    return entity, rest


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    p = config.cmd_prefix
    register_help(
        client,
        "Channels",
        [
            f"{p}channels — list channels you can post to",
            f"{p}cset <channel> — set default channel",
            f"{p}cpost [channel] <text> — post (reply to copy media)",
            f"{p}cedit <text> — edit replied channel post",
            f"{p}cpin / {p}cunpin — pin/unpin replied post",
            f"{p}cstat [channel] — channel info",
            f"{p}csched <when> [channel] <text> — schedule a post",
            f"{p}cupload [channel] [filepath] — upload file or replied media",
        ],
    )

    @command(client, config, r"channels$")
    async def channels_cmd(event) -> None:
        await edit_or_reply(event, "Scanning your dialogs…")
        lines: list[str] = []
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if isinstance(entity, Channel) and entity.broadcast:
                # Prefer channels where we are creator or admin with post rights
                can_post = bool(entity.creator) or bool(
                    getattr(entity, "admin_rights", None)
                    and getattr(entity.admin_rights, "post_messages", False)
                )
                if not can_post:
                    continue
                uname = f"@{entity.username}" if entity.username else f"id:{entity.id}"
                lines.append(f"• {dialog.title} (`{uname}`)")
        if not lines:
            await edit_or_reply(
                event,
                "No postable channels found. Make sure you are admin/creator.",
            )
            return
        await edit_or_reply(event, "**Your channels**\n" + "\n".join(lines[:50]))

    @command(client, config, r"cset(?:\s+(.+))?$")
    async def cset_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        if not raw:
            current = await db.get_setting(DEFAULT_CHANNEL_KEY)
            if current:
                await edit_or_reply(event, f"Default channel: `{current}`")
            else:
                await edit_or_reply(event, f"No default set. Usage: `{p}cset @mychannel`")
            return
        try:
            entity = await _resolve_channel(client, raw)
        except Exception as exc:  # noqa: BLE001
            await edit_or_reply(event, f"Could not set channel: `{exc}`")
            return
        ref = f"@{entity.username}" if entity.username else str(entity.id)
        await db.set_setting(DEFAULT_CHANNEL_KEY, ref)
        await edit_or_reply(event, f"Default channel set to **{entity.title}** (`{ref}`)")

    @command(client, config, r"cpost(?:\s+(.+))?$")
    async def cpost_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        first, _, rest = raw.partition(" ")
        first = first.strip()
        rest = rest.strip()
        try:
            if raw:
                channel, text = await _pick_channel(client, db, config, first or None, rest)
            else:
                channel = await _get_default_channel(client, db)
                if channel is None:
                    raise ValueError(
                        f"No channel given and no default set. Use `{p}cset @channel`."
                    )
                text = ""
        except ValueError as exc:
            await edit_or_reply(event, str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            await edit_or_reply(event, f"Channel error: `{exc}`")
            return

        try:
            if event.is_reply:
                reply = await event.get_reply_message()
                if reply and reply.media:
                    await client.send_file(
                        channel,
                        file=reply.media,
                        caption=text or reply.text or "",
                    )
                elif reply:
                    await client.send_message(channel, text or reply.text or "")
                else:
                    if not text:
                        await edit_or_reply(event, "Nothing to post.")
                        return
                    await client.send_message(channel, text)
            else:
                if not text:
                    await edit_or_reply(
                        event,
                        f"Usage: `{p}cpost [channel] text` or reply to media.",
                    )
                    return
                await client.send_message(channel, text)
        except Exception as exc:  # noqa: BLE001
            await edit_or_reply(event, f"Post failed: `{exc}`")
            return

        await edit_or_reply(event, f"Posted to **{channel.title}**.")

    @command(client, config, r"cedit(?:\s+(.+))?$")
    async def cedit_cmd(event) -> None:
        text = (event.pattern_match.group(1) or "").strip()
        if not event.is_reply or not text:
            await edit_or_reply(event, f"Reply to a channel post: `{p}cedit new text`")
            return
        reply = await event.get_reply_message()
        try:
            await client.edit_message(reply.chat_id, reply.id, text)
            await edit_or_reply(event, "Post updated.")
        except Exception as exc:  # noqa: BLE001
            await edit_or_reply(event, f"Edit failed: `{exc}`")

    @command(client, config, r"cpin$")
    async def cpin_cmd(event) -> None:
        if not event.is_reply:
            await edit_or_reply(event, f"Reply to a channel post, then `{p}cpin`.")
            return
        reply = await event.get_reply_message()
        try:
            await client.pin_message(reply.chat_id, reply.id, notify=False)
            await edit_or_reply(event, "Pinned.")
        except Exception as exc:  # noqa: BLE001
            await edit_or_reply(event, f"Pin failed: `{exc}`")

    @command(client, config, r"cunpin$")
    async def cunpin_cmd(event) -> None:
        if not event.is_reply:
            await edit_or_reply(
                event,
                f"Reply to a pinned post, then `{p}cunpin` "
                f"(or use in the channel chat).",
            )
            return
        reply = await event.get_reply_message()
        try:
            await client.unpin_message(reply.chat_id, reply.id)
            await edit_or_reply(event, "Unpinned.")
        except Exception as exc:  # noqa: BLE001
            await edit_or_reply(event, f"Unpin failed: `{exc}`")

    @command(client, config, r"cstat(?:\s+(.+))?$")
    async def cstat_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        try:
            if raw:
                channel = await _resolve_channel(client, raw)
            else:
                channel = await _get_default_channel(client, db)
                if channel is None and event.is_channel:
                    chat = await event.get_chat()
                    if isinstance(chat, Channel) and chat.broadcast:
                        channel = chat
                if channel is None:
                    raise ValueError(
                        f"Pass a channel or set default with `{p}cset @channel`."
                    )
            full = await client(GetFullChannelRequest(channel))
        except ValueError as exc:
            await edit_or_reply(event, str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            await edit_or_reply(event, f"Could not load channel: `{exc}`")
            return

        uname = f"@{channel.username}" if channel.username else "—"
        about = full.full_chat.about or "—"
        participants = getattr(full.full_chat, "participants_count", None) or "—"
        text = (
            f"**{channel.title}**\n"
            f"• Username: {uname}\n"
            f"• ID: `{channel.id}`\n"
            f"• Subscribers: `{participants}`\n"
            f"• About: {about}"
        )
        await edit_or_reply(event, text)

    @command(client, config, r"csched(?:\s+(.+))?$")
    async def csched_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        if not raw:
            await edit_or_reply(
                event,
                f"Usage: `{p}csched 2h [channel] your post text`",
            )
            return

        tokens = raw.split(maxsplit=2)
        when_token = tokens[0]
        delta = parse_duration(when_token)
        if delta is None:
            await edit_or_reply(
                event,
                "Could not parse time. Use `10m`, `2h`, `1d`, `1h30m`.",
            )
            return

        remainder = " ".join(tokens[1:]).strip()
        if not remainder and not event.is_reply:
            await edit_or_reply(event, "Provide post text or reply to media.")
            return

        first, _, rest = remainder.partition(" ")
        first = first.strip()
        rest = rest.strip()
        try:
            if remainder:
                channel, text = await _pick_channel(
                    client, db, config, first or None, rest
                )
            else:
                channel = await _get_default_channel(client, db)
                if channel is None:
                    raise ValueError(
                        f"No channel given and no default set. Use `{p}cset @channel`."
                    )
                text = ""
        except ValueError as exc:
            await edit_or_reply(event, str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            await edit_or_reply(event, f"Channel error: `{exc}`")
            return

        schedule_date = datetime.now(timezone.utc) + delta
        try:
            if event.is_reply:
                reply = await event.get_reply_message()
                if reply and reply.media:
                    await client.send_file(
                        channel,
                        file=reply.media,
                        caption=text or reply.text or "",
                        schedule=schedule_date,
                    )
                else:
                    body = text or (reply.text if reply else "")
                    if not body:
                        await edit_or_reply(event, "Nothing to schedule.")
                        return
                    await client.send_message(
                        channel, body, schedule=schedule_date
                    )
            else:
                if not text:
                    await edit_or_reply(event, "Provide post text.")
                    return
                await client.send_message(channel, text, schedule=schedule_date)
        except Exception as exc:  # noqa: BLE001
            await edit_or_reply(event, f"Schedule failed: `{exc}`")
            return

        await edit_or_reply(
            event,
            f"Scheduled on **{channel.title}** for **{format_local(schedule_date)}**.",
        )

    @command(client, config, r"cupload(?:\s+(.+))?$")
    async def cupload_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        first, _, rest = raw.partition(" ")
        first = first.strip()
        rest = rest.strip()

        channel = None
        file_path = ""
        try:
            if first:
                try:
                    channel = await _resolve_channel(client, first)
                    file_path = rest
                except Exception:
                    channel = await _get_default_channel(client, db)
                    file_path = raw
            else:
                channel = await _get_default_channel(client, db)

            if channel is None:
                raise ValueError(
                    f"No channel given and no default set. Use `{p}cset @channel`."
                )
        except ValueError as exc:
            await edit_or_reply(event, str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            await edit_or_reply(event, f"Channel error: `{exc}`")
            return

        try:
            if event.is_reply:
                reply = await event.get_reply_message()
                if not reply or not reply.media:
                    await edit_or_reply(
                        event,
                        "Reply to media, or pass a local file path.",
                    )
                    return
                # Only upload media types
                if not isinstance(
                    reply.media, (MessageMediaPhoto, MessageMediaDocument)
                ) and not reply.media:
                    await edit_or_reply(event, "Unsupported media.")
                    return
                await client.send_file(channel, file=reply.media, caption=file_path or "")
            else:
                if not file_path:
                    await edit_or_reply(
                        event,
                        f"Usage: `{p}cupload [channel] C:\\path\\to\\file.jpg` "
                        f"or reply to media.",
                    )
                    return
                path = Path(file_path.strip().strip('"'))
                if not path.is_file():
                    await edit_or_reply(event, f"File not found: `{path}`")
                    return
                await client.send_file(channel, file=str(path))
        except Exception as exc:  # noqa: BLE001
            await edit_or_reply(event, f"Upload failed: `{exc}`")
            return

        await edit_or_reply(event, f"Uploaded to **{channel.title}**.")
