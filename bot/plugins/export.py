"""Export notes/tags/snippets/filters to Saved Messages."""

from __future__ import annotations

import json
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
        "Export",
        [
            f"{p}export — dump notes/tags/snips/filters JSON → Saved Messages",
        ],
    )

    @command(client, config, r"export$")
    async def export_cmd(event) -> None:
        bundle = await db.export_bundle()
        bundle["exported_at"] = to_iso(utc_now())
        path = config.downloads_dir / f"userbot-export-{utc_now().strftime('%Y%m%d-%H%M%S')}.json"
        path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
        me = await client.get_me()
        await client.send_file(
            me,
            str(path),
            caption=(
                f"**Userbot export**\n"
                f"notes={len(bundle['notes'])} "
                f"tags={len(bundle['tags'])} "
                f"snips={len(bundle['snippets'])} "
                f"filters={len(bundle['filters'])}"
            ),
        )
        await edit_or_reply(event, "Export sent to **Saved Messages**.")
