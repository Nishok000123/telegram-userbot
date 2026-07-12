"""Save restricted Telegram posts by link (inspired by VJ-Save-Restricted-Content).

Personal use only. Your account must already be able to view the post
(member of private chat, etc.). Supports forum topic links.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from telethon.errors import FloodWaitError, InviteHashExpiredError, UserAlreadyParticipantError
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.types import Message

from bot.utils.decorators import command, edit_or_reply, register_help

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database

_cancel = False
_busy = False

# Forum topic: t.me/c/ID/TOPIC/MSG or t.me/user/TOPIC/MSG
_TOPIC_PRIVATE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?t\.me/c/(\d+)/(\d+)/(\d+)(?:\s*-\s*(\d+))?",
    re.IGNORECASE,
)
_TOPIC_PUBLIC_RE = re.compile(
    r"(?:https?://)?(?:www\.)?t\.me/([^/\s+]+)/(\d+)/(\d+)(?:\s*-\s*(\d+))?",
    re.IGNORECASE,
)
# Classic (no topic): t.me/c/ID/MSG, t.me/b/bot/MSG, t.me/user/MSG
_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?t\.me/(?:c/(\d+)/|b/([^/\s]+)/|([^/\s+]+)/)"
    r"(\d+)(?:\s*-\s*(\d+))?",
    re.IGNORECASE,
)
_INVITE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?t\.me/(?:\+|joinchat/)([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)


class ParsedLink(NamedTuple):
    chat_ref: Any
    from_id: int
    to_id: int
    topic_id: int | None


def _parse_post_link(text: str) -> ParsedLink | None:
    """Parse classic or forum-topic t.me links."""
    text = text.strip()

    m = _TOPIC_PRIVATE_RE.search(text)
    if m:
        private_id, topic_s, from_s, to_s = m.groups()
        from_id = int(from_s)
        to_id = int(to_s) if to_s else from_id
        if to_id < from_id:
            from_id, to_id = to_id, from_id
        return ParsedLink(
            chat_ref=int(f"-100{private_id}"),
            from_id=from_id,
            to_id=to_id,
            topic_id=int(topic_s),
        )

    m = _TOPIC_PUBLIC_RE.search(text)
    if m:
        user, topic_s, from_s, to_s = m.groups()
        # Avoid matching classic 2-segment as topic (user/msg only)
        # Topic form has THREE numeric segments after username — already required.
        # But classic public is user/msg — two numbers. Topic is user/topic/msg — three.
        # _TOPIC_PUBLIC_RE requires two nums after user, so user/123/456 = topic 123 msg 456.
        # Classic user/123 matches _LINK_RE not this (needs two groups after user).
        if user.lower() in {"c", "b", "joinchat"}:
            pass
        else:
            from_id = int(from_s)
            to_id = int(to_s) if to_s else from_id
            if to_id < from_id:
                from_id, to_id = to_id, from_id
            return ParsedLink(
                chat_ref=user,
                from_id=from_id,
                to_id=to_id,
                topic_id=int(topic_s),
            )

    m = _LINK_RE.search(text)
    if not m:
        return None
    private_id, bot_user, public_user, from_s, to_s = m.groups()
    from_id = int(from_s)
    to_id = int(to_s) if to_s else from_id
    if to_id < from_id:
        from_id, to_id = to_id, from_id

    if private_id:
        chat_ref: Any = int(f"-100{private_id}")
    elif bot_user:
        chat_ref = bot_user
    else:
        chat_ref = public_user
    return ParsedLink(chat_ref=chat_ref, from_id=from_id, to_id=to_id, topic_id=None)


async def _sleep_wait(seconds: float) -> None:
    if seconds > 0:
        await asyncio.sleep(seconds)


async def _get_message(
    client: "TelegramClient",
    chat_ref: Any,
    msg_id: int,
    topic_id: int | None,
) -> Message | None:
    """Fetch one message; for topics try reply_to=topic_id first."""
    if topic_id is not None:
        try:
            msg = await client.get_messages(
                chat_ref, ids=msg_id, reply_to=topic_id
            )
            if msg and isinstance(msg, Message):
                return msg
        except Exception:
            pass
        # Fallback: plain get by id (works if ids are unique in channel)
    msg = await client.get_messages(chat_ref, ids=msg_id)
    if msg and isinstance(msg, Message):
        return msg
    return None


async def _send_one(
    client: "TelegramClient",
    dest_chat: int,
    src_msg: Message,
    downloads_dir: Path,
) -> None:
    """Copy one message to dest. Prefer forward; fall back to download+upload."""
    try:
        await client.forward_messages(dest_chat, src_msg)
        return
    except Exception:
        pass

    if src_msg.media:
        path = await client.download_media(src_msg, file=str(downloads_dir / "save_"))
        if not path:
            if src_msg.message:
                await client.send_message(dest_chat, src_msg.message)
            else:
                raise RuntimeError("empty media download")
            return
        try:
            await client.send_file(
                dest_chat,
                path,
                caption=src_msg.message or None,
            )
        finally:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass
        return

    if src_msg.message:
        await client.send_message(dest_chat, src_msg.message)
        return

    raise RuntimeError("nothing to save")


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    p = config.cmd_prefix
    register_help(
        client,
        "Save Restricted",
        [
            f"{p}save <link> — save post(s) by t.me link (range + topics ok)",
            f"{p}save vault <link> — save into UB Vault if configured",
            f"{p}join <invite> — join private chat via invite link",
            f"{p}scancel — cancel running .save batch",
        ],
    )

    @command(client, config, r"scancel$")
    async def scancel_cmd(event) -> None:
        global _cancel
        if not _busy:
            await edit_or_reply(event, "No save job running.")
            return
        _cancel = True
        await edit_or_reply(event, "Cancel requested…")

    @command(client, config, r"join(?:\s+(.+))?$")
    async def join_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        if not raw:
            await edit_or_reply(event, f"Usage: `{p}join https://t.me/+xxxxx`")
            return
        m = _INVITE_RE.search(raw)
        if not m:
            await edit_or_reply(event, "Need invite link like `https://t.me/+hash`")
            return
        invite_hash = m.group(1)
        try:
            await client(ImportChatInviteRequest(invite_hash))
            await edit_or_reply(event, "Joined chat.")
        except UserAlreadyParticipantError:
            await edit_or_reply(event, "Already a member.")
        except InviteHashExpiredError:
            await edit_or_reply(event, "Invite expired or invalid.")
        except FloodWaitError as fw:
            await edit_or_reply(event, f"FloodWait `{fw.seconds}s`. Try later.")
        except Exception as exc:  # noqa: BLE001
            try:
                await client(CheckChatInviteRequest(invite_hash))
            except Exception:
                pass
            await edit_or_reply(event, f"Join failed: `{exc}`")

    @command(client, config, r"save(?:\s+(.+))?$")
    async def save_cmd(event) -> None:
        global _busy, _cancel

        raw = (event.pattern_match.group(1) or "").strip()
        if not raw:
            await edit_or_reply(
                event,
                f"Usage:\n"
                f"`{p}save https://t.me/channel/123`\n"
                f"`{p}save https://t.me/c/1234567890/100-110`\n"
                f"`{p}save https://t.me/c/ID/TOPIC/MSG` (forum topic)\n"
                f"`{p}save vault <link>` — into UB Vault\n"
                f"`{p}save https://t.me/b/botuser/55`\n\n"
                f"Private chat: `{p}join` invite first if needed.",
            )
            return

        dest = event.chat_id
        link_text = raw
        if raw.lower().startswith("vault "):
            link_text = raw[6:].strip()
            vault_raw = await db.get_setting("vault_chat_id")
            if not vault_raw:
                await edit_or_reply(
                    event, f"No vault. Run `{p}vault setup` first."
                )
                return
            dest = int(vault_raw)

        parsed = _parse_post_link(link_text)
        if not parsed:
            await edit_or_reply(event, "Could not parse t.me post link.")
            return

        if _busy:
            await edit_or_reply(
                event,
                f"Already saving. Wait, or `{p}scancel`.",
            )
            return

        chat_ref, from_id, to_id, topic_id = parsed
        total = to_id - from_id + 1
        _busy = True
        _cancel = False
        done = 0
        failed = 0
        cancelled = False
        topic_note = f" topic `{topic_id}`" if topic_id else ""

        await edit_or_reply(
            event,
            f"**Saving…** `0/{total}`{topic_note}\n`{link_text}`\n"
            f"Cancel: `{p}scancel`",
        )

        try:
            for msgid in range(from_id, to_id + 1):
                if _cancel:
                    cancelled = True
                    break
                try:
                    msg = await _get_message(client, chat_ref, msgid, topic_id)
                    if not msg:
                        failed += 1
                    else:
                        await _send_one(client, dest, msg, config.downloads_dir)
                        done += 1
                except FloodWaitError as fw:
                    await asyncio.sleep(fw.seconds + 1)
                    try:
                        msg = await _get_message(client, chat_ref, msgid, topic_id)
                        if msg:
                            await _send_one(client, dest, msg, config.downloads_dir)
                            done += 1
                        else:
                            failed += 1
                    except Exception:
                        failed += 1
                except Exception:
                    failed += 1

                current = done + failed
                if current % 5 == 0 or current == total or _cancel:
                    try:
                        await event.edit(
                            f"**Saving…** `{current}/{total}` "
                            f"(ok `{done}` / fail `{failed}`){topic_note}\n"
                            f"`{link_text}`"
                        )
                    except Exception:
                        pass

                await _sleep_wait(config.waiting_time)
        finally:
            _busy = False
            _cancel = False

        label = "Cancelled" if cancelled else "Done"
        await edit_or_reply(
            event,
            f"**{label}**\n"
            f"ok `{done}` / fail `{failed}` / total `{total}`{topic_note}\n"
            f"`{link_text}`",
        )
