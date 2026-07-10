"""Chat hygiene: purge, stash, clone, mute, archive, read, block, ghost."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from telethon.tl.functions.account import UpdateNotifySettingsRequest
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.types import InputNotifyPeer, InputPeerNotifySettings

from bot.utils.decorators import command, edit_or_reply, register_help
from bot.utils.peers import display_user, get_reply_or_fail, resolve_user
from bot.utils.timeparse import parse_duration

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    p = config.cmd_prefix
    register_help(
        client,
        "Chat tools",
        [
            f"{p}purge <n> — delete your last n messages here",
            f"{p}stash — copy replied msg to Saved Messages",
            f"{p}clone [@chat|saved] — copy replied msg to target",
            f"{p}mute [2h] — mute this chat (default 1h)",
            f"{p}unmute — unmute this chat",
            f"{p}archive / {p}unarchive — archive this chat",
            f"{p}read — mark this chat read",
            f"{p}block / {p}unblock — block replied user",
            f"{p}ghost [n] — peek last n msgs without read receipts",
        ],
    )

    @command(client, config, r"purge(?:\s+(\d+))?$")
    async def purge_cmd(event) -> None:
        raw = event.pattern_match.group(1)
        if not raw:
            await edit_or_reply(event, f"Usage: `{p}purge <n>` (1–100)")
            return
        n = int(raw)
        if n < 1 or n > 100:
            await edit_or_reply(event, "Use a number from 1 to 100.")
            return

        me = await client.get_me()
        deleted = 0
        # Include the command message itself in the sweep
        async for msg in client.iter_messages(event.chat_id, from_user=me, limit=n + 5):
            try:
                await msg.delete()
                deleted += 1
            except Exception:
                pass
            if deleted >= n:
                break
        # Command may already be gone; try status in chat
        try:
            await client.send_message(event.chat_id, f"Purged **{deleted}** of your messages.")
        except Exception:
            pass

    @command(client, config, r"stash$")
    async def stash_cmd(event) -> None:
        reply, err = await get_reply_or_fail(event)
        if err or reply is None:
            await edit_or_reply(event, err or "No reply.")
            return
        me = await client.get_me()
        await client.forward_messages(me, reply)
        await edit_or_reply(event, "Stashed to **Saved Messages**.")

    @command(client, config, r"clone(?:\s+(.*))?$")
    async def clone_cmd(event) -> None:
        reply, err = await get_reply_or_fail(event)
        if err or reply is None:
            await edit_or_reply(event, err or "No reply.")
            return
        target_raw = (event.pattern_match.group(1) or "saved").strip()
        me = await client.get_me()
        if target_raw.lower() in {"saved", "me", "self"}:
            target = me
            label = "Saved Messages"
        else:
            try:
                target = await client.get_entity(target_raw)
                label = getattr(target, "title", None) or getattr(
                    target, "username", None
                ) or str(getattr(target, "id", target_raw))
            except Exception:
                await edit_or_reply(event, f"Cannot find chat `{target_raw}`.")
                return
        try:
            await client.forward_messages(target, reply)
        except Exception:
            # Forward may fail (restricted); try copy
            await client.send_message(target, reply.message or "", file=reply.media)
        await edit_or_reply(event, f"Cloned to **{label}**.")

    @command(client, config, r"mute(?:\s+(\S+))?$")
    async def mute_cmd(event) -> None:
        when = (event.pattern_match.group(1) or "1h").strip()
        delta = parse_duration(when)
        if delta is None:
            await edit_or_reply(event, f"Usage: `{p}mute 2h` (forms: `30m`, `2h`, `1d`)")
            return
        mute_until = int(time.time() + delta.total_seconds())
        peer = InputNotifyPeer(await event.get_input_chat())
        await client(
            UpdateNotifySettingsRequest(
                peer=peer,
                settings=InputPeerNotifySettings(
                    mute_until=mute_until,
                    show_previews=False,
                ),
            )
        )
        await edit_or_reply(event, f"Muted this chat for **{when}**.")

    @command(client, config, r"unmute$")
    async def unmute_cmd(event) -> None:
        peer = InputNotifyPeer(await event.get_input_chat())
        await client(
            UpdateNotifySettingsRequest(
                peer=peer,
                settings=InputPeerNotifySettings(mute_until=0),
            )
        )
        await edit_or_reply(event, "Unmuted this chat.")

    @command(client, config, r"archive$")
    async def archive_cmd(event) -> None:
        await client.edit_folder(event.chat_id, folder=1)
        await edit_or_reply(event, "Archived this chat.")

    @command(client, config, r"unarchive$")
    async def unarchive_cmd(event) -> None:
        await client.edit_folder(event.chat_id, folder=0)
        await edit_or_reply(event, "Unarchived this chat.")

    @command(client, config, r"read$")
    async def read_cmd(event) -> None:
        await client.send_read_acknowledge(event.chat_id)
        await edit_or_reply(event, "Marked read.")

    @command(client, config, r"block(?:\s+(.*))?$")
    async def block_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        tokens = raw.split() if raw else []
        user, _, err = await resolve_user(client, event, tokens)
        if err or user is None:
            await edit_or_reply(event, err or "No user.")
            return
        entity = await client.get_input_entity(user)
        await client(BlockRequest(id=entity))
        await edit_or_reply(event, f"Blocked **{display_user(user)}**.")

    @command(client, config, r"unblock(?:\s+(.*))?$")
    async def unblock_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        tokens = raw.split() if raw else []
        user, _, err = await resolve_user(client, event, tokens)
        if err or user is None:
            await edit_or_reply(event, err or "No user.")
            return
        entity = await client.get_input_entity(user)
        await client(UnblockRequest(id=entity))
        await edit_or_reply(event, f"Unblocked **{display_user(user)}**.")

    @command(client, config, r"ghost(?:\s+(\d+))?$")
    async def ghost_cmd(event) -> None:
        """Fetch recent messages without sending read receipts."""
        n = int(event.pattern_match.group(1) or "5")
        n = max(1, min(n, 20))
        peer = await event.get_input_chat()
        history = await client(
            GetHistoryRequest(
                peer=peer,
                offset_id=0,
                offset_date=None,
                add_offset=0,
                limit=n,
                max_id=0,
                min_id=0,
                hash=0,
            )
        )
        lines = [f"**Ghost peek** (last {n}, no read receipt)"]
        for msg in reversed(list(history.messages)):
            sender = ""
            text = getattr(msg, "message", None) or "[media/service]"
            text = text.replace("\n", " ")
            if len(text) > 120:
                text = text[:117] + "..."
            lines.append(f"• `{getattr(msg, 'id', '?')}` {text}")
        await edit_or_reply(event, "\n".join(lines))
