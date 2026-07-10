"""Quote replied text as a simple image card."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

from bot.utils.decorators import command, edit_or_reply, register_help
from bot.utils.peers import display_user, get_reply_or_fail

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database


def _make_quote_image(text: str, author: str, out_path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 900, 500
    img = Image.new("RGB", (width, height), (24, 28, 36))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 32)
        font_small = ImageFont.truetype("DejaVuSans.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
        font_small = font

    wrapped = textwrap.fill(text.strip() or "…", width=40)
    draw.rectangle((40, 40, width - 40, height - 40), outline=(90, 110, 140), width=2)
    draw.text((70, 80), wrapped, fill=(235, 240, 245), font=font)
    draw.text((70, height - 90), f"— {author}", fill=(160, 175, 195), font=font_small)
    img.save(out_path, format="PNG")


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    p = config.cmd_prefix
    register_help(
        client,
        "Quote",
        [
            f"{p}quote — reply to text → quote image",
        ],
    )

    @command(client, config, r"quote$")
    async def quote_cmd(event) -> None:
        reply, err = await get_reply_or_fail(event)
        if err or reply is None:
            await edit_or_reply(event, err or "No reply.")
            return
        text = (reply.message or "").strip()
        if not text:
            await edit_or_reply(event, "Replied message has no text.")
            return

        sender = await reply.get_sender()
        author = display_user(sender) if sender else "Unknown"
        if getattr(sender, "username", None):
            author = f"{author} (@{sender.username})"

        out = config.downloads_dir / f"quote-{reply.id}.png"
        try:
            _make_quote_image(text[:500], author, out)
        except Exception as exc:  # noqa: BLE001
            await edit_or_reply(event, f"Quote image failed: {exc}")
            return

        await client.send_file(event.chat_id, str(out), reply_to=reply.id)
        try:
            await event.delete()
        except Exception:
            await edit_or_reply(event, "Quoted.")
