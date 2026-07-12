"""Real Telegram folder (DialogFilter) management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telethon.tl.functions.messages import (
    GetDialogFiltersRequest,
    UpdateDialogFilterRequest,
)
from telethon.tl.types import DialogFilter, TextWithEntities

from bot.utils.decorators import command, edit_or_reply, register_help

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database


def _filter_title(f: Any) -> str:
    title = getattr(f, "title", None)
    if title is None:
        return ""
    if isinstance(title, str):
        return title
    return getattr(title, "text", None) or str(title)


def _title_obj(name: str) -> TextWithEntities | str:
    try:
        return TextWithEntities(text=name, entities=[])
    except Exception:
        return name


async def _list_filters(client: "TelegramClient") -> list[Any]:
    result = await client(GetDialogFiltersRequest())
    if isinstance(result, list):
        filters = result
    else:
        filters = getattr(result, "filters", None) or list(result)
    out = []
    for f in filters:
        if hasattr(f, "id") and hasattr(f, "include_peers"):
            out.append(f)
    return out


async def _find_filter(client: "TelegramClient", name: str) -> Any | None:
    name_l = name.lower()
    for f in await _list_filters(client):
        if _filter_title(f).lower() == name_l:
            return f
    return None


async def _next_filter_id(client: "TelegramClient") -> int:
    used = {int(f.id) for f in await _list_filters(client)}
    for i in range(2, 255):
        if i not in used:
            return i
    raise RuntimeError("No free folder id (2–254)")


async def _resolve_peer(client: "TelegramClient", event, token: str | None):
    if token:
        return await client.get_input_entity(token)
    return await event.get_input_chat()


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    p = config.cmd_prefix
    register_help(
        client,
        "Folders",
        [
            f"{p}folder list — list Telegram folders",
            f"{p}folder new <name> — create folder",
            f"{p}folder add <name> [@peer] — add chat to folder",
            f"{p}folder rm <name> [@peer] — remove chat from folder",
            f"{p}folder del <name> — delete folder",
        ],
    )

    @command(client, config, r"folder(?:\s+(.*))?$")
    async def folder_cmd(event) -> None:
        raw = (event.pattern_match.group(1) or "").strip()
        if not raw:
            await edit_or_reply(
                event,
                f"Usage:\n`{p}folder list`\n`{p}folder new Name`\n"
                f"`{p}folder add Name [@peer]`\n"
                f"`{p}folder rm Name [@peer]`\n`{p}folder del Name`",
            )
            return

        parts = raw.split(maxsplit=2)
        action = parts[0].lower()

        if action == "list":
            filters = await _list_filters(client)
            if not filters:
                await edit_or_reply(event, "No custom folders.")
                return
            lines = ["**Folders**"]
            for f in filters:
                n = len(getattr(f, "include_peers", []) or [])
                lines.append(f"• `{_filter_title(f)}` (id `{f.id}`, {n} chats)")
            await edit_or_reply(event, "\n".join(lines))
            return

        if action == "new":
            if len(parts) < 2:
                await edit_or_reply(event, f"Usage: `{p}folder new <name>`")
                return
            name = parts[1] if len(parts) == 2 else f"{parts[1]} {parts[2]}"
            name = name.strip()
            if await _find_filter(client, name):
                await edit_or_reply(event, f"Folder `{name}` already exists.")
                return
            try:
                fid = await _next_filter_id(client)
                filt = DialogFilter(
                    id=fid,
                    title=_title_obj(name),
                    pinned_peers=[],
                    include_peers=[],
                    exclude_peers=[],
                    contacts=False,
                    non_contacts=False,
                    groups=False,
                    broadcasts=False,
                    bots=False,
                    exclude_muted=False,
                    exclude_read=False,
                    exclude_archived=False,
                )
                await client(UpdateDialogFilterRequest(id=fid, filter=filt))
                await edit_or_reply(event, f"Created folder **{name}** (`{fid}`).")
            except Exception as exc:  # noqa: BLE001
                await edit_or_reply(event, f"Create folder failed: `{exc}`")
            return

        if action in {"add", "rm", "remove"}:
            if len(parts) < 2:
                await edit_or_reply(
                    event, f"Usage: `{p}folder {action} <name> [@peer]`"
                )
                return
            # name may be multi-word if no peer; peer is last token if @ or digit
            rest = raw.split(maxsplit=1)[1]
            tokens = rest.split()
            peer_token = None
            if len(tokens) >= 2 and (
                tokens[-1].startswith("@") or tokens[-1].lstrip("-").isdigit()
            ):
                peer_token = tokens[-1]
                name = " ".join(tokens[:-1])
            else:
                name = rest.strip()

            filt = await _find_filter(client, name)
            if filt is None:
                await edit_or_reply(event, f"No folder `{name}`.")
                return
            try:
                peer = await _resolve_peer(client, event, peer_token)
            except Exception:
                await edit_or_reply(event, f"Cannot resolve peer `{peer_token}`.")
                return

            include = list(getattr(filt, "include_peers", []) or [])
            # Compare by stringified peer
            peer_key = str(peer)
            existing_keys = {str(x) for x in include}

            if action == "add":
                if peer_key in existing_keys:
                    await edit_or_reply(event, "Chat already in folder.")
                    return
                include.append(peer)
            else:
                new_include = []
                removed = False
                # Match by resolving each — compare user_id/channel_id if possible
                target = await client.get_entity(peer)
                target_id = getattr(target, "id", None)
                for item in include:
                    try:
                        ent = await client.get_entity(item)
                        if getattr(ent, "id", None) == target_id:
                            removed = True
                            continue
                    except Exception:
                        pass
                    new_include.append(item)
                if not removed:
                    await edit_or_reply(event, "Chat not in that folder.")
                    return
                include = new_include

            filt.include_peers = include
            try:
                await client(UpdateDialogFilterRequest(id=filt.id, filter=filt))
                verb = "Added to" if action == "add" else "Removed from"
                await edit_or_reply(event, f"{verb} **{_filter_title(filt)}**.")
            except Exception as exc:  # noqa: BLE001
                await edit_or_reply(event, f"Update folder failed: `{exc}`")
            return

        if action in {"del", "delete"}:
            if len(parts) < 2:
                await edit_or_reply(event, f"Usage: `{p}folder del <name>`")
                return
            name = raw.split(maxsplit=1)[1].strip()
            filt = await _find_filter(client, name)
            if filt is None:
                await edit_or_reply(event, f"No folder `{name}`.")
                return
            try:
                await client(UpdateDialogFilterRequest(id=filt.id, filter=None))
                await edit_or_reply(event, f"Deleted folder **{name}**.")
            except Exception as exc:  # noqa: BLE001
                await edit_or_reply(event, f"Delete folder failed: `{exc}`")
            return

        await edit_or_reply(event, f"Unknown action. Try `{p}help`.")
