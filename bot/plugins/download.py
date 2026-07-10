"""Download replied media to data/downloads."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from bot.utils.decorators import command, edit_or_reply, register_help
from bot.utils.timeparse import to_iso, utc_now

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    p = config.cmd_prefix
    register_help(
        client,
        "Media",
        [
            f"{p}dl — reply to a media message to download it",
        ],
    )

    @command(client, config, r"dl$")
    async def dl_cmd(event) -> None:
        if not event.is_reply:
            await edit_or_reply(event, f"Reply to a media message, then type `{p}dl`.")
            return

        reply = await event.get_reply_message()
        if reply is None or not reply.media:
            await edit_or_reply(event, "That message has no downloadable media.")
            return

        await edit_or_reply(event, "Downloading…")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_dir = Path(config.downloads_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            path = await client.download_media(
                reply,
                file=str(target_dir / f"{stamp}_"),
            )
        except Exception as exc:  # noqa: BLE001
            await edit_or_reply(event, f"Download failed: `{exc}`")
            return

        if not path:
            await edit_or_reply(event, "Download failed (empty result).")
            return

        path_obj = Path(path)
        source = f"chat={event.chat_id} msg={reply.id}"
        await db.log_download(str(path_obj), source, to_iso(utc_now()))
        await edit_or_reply(
            event,
            f"**Downloaded**\n`{path_obj.name}`\nFolder: `data/downloads/`",
        )
