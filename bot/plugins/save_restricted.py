"""Save restricted Telegram posts by link (inspired by VJ-Save-Restricted-Content).

Personal use only. Your account must already be able to view the post
(member of private chat, etc.).
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from telethon.errors import FloodWaitError, InviteHashExpiredError, UserAlreadyParticipantError
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.types import Message

from bot.utils.decorators import command, edit_or_reply, register_help

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database

# Cancel flag for the running batch (single-user personal bot)
_cancel = False
_busy = False

_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?t\.me/(?:c/(\d+)/|b/([^/\s]+)/|([^/\s+]+)/)"
    r"(\d+)(?:\s*-\s*(\d+))?",
    re.IGNORECASE,
)
_INVITE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?t\.me/(?:\+|joinchat/)([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)


def _parse_post_link(text: str) -> tuple[Any, int, int] | None:
    """Return (chat_ref, from_id, to_id) or None."""
    m = _LINK_RE.search(text.strip())
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
    return chat_ref, from_id, to_id


async def _sleep_wait(seconds: float) -> None:
    if seconds > 0:
        await asyncio.sleep(seconds)


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
            f"{p}save <link> — save post(s) by t.me link (range ok)",
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
            # Sometimes CheckChatInvite helps diagnose
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
                f"`{p}save https://t.me/b/botuser/55`\n\n"
                f"Private chat: `{p}join` invite first if needed.",
            )
            return

        parsed = _parse_post_link(raw)
        if not parsed:
            await edit_or_reply(event, "Could not parse t.me post link.")
            return

        if _busy:
            await edit_or_reply(
                event,
                f"Already saving. Wait, or `{p}scancel`.",
            )
            return

        chat_ref, from_id, to_id = parsed
        total = to_id - from_id + 1
        dest = event.chat_id
        _busy = True
        _cancel = False
        done = 0
        failed = 0
        cancelled = False

        await edit_or_reply(
            event,
            f"**Saving…** `0/{total}`\n`{raw}`\nCancel: `{p}scancel`",
        )

        try:
            for msgid in range(from_id, to_id + 1):
                if _cancel:
                    cancelled = True
                    break
                try:
                    msg = await client.get_messages(chat_ref, ids=msgid)
                    if not msg or not isinstance(msg, Message):
                        failed += 1
                    else:
                        await _send_one(client, dest, msg, config.downloads_dir)
                        done += 1
                except FloodWaitError as fw:
                    await asyncio.sleep(fw.seconds + 1)
                    try:
                        msg = await client.get_messages(chat_ref, ids=msgid)
                        if msg and isinstance(msg, Message):
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
                            f"(ok `{done}` / fail `{failed}`)\n`{raw}`"
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
            f"ok `{done}` / fail `{failed}` / total `{total}`\n"
            f"`{raw}`",
        )
