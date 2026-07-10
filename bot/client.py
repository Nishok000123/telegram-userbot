"""Telethon client factory."""

from __future__ import annotations

from telethon import TelegramClient
from telethon.sessions import StringSession

from bot.config import Config


def create_client(config: Config) -> TelegramClient:
    if config.session_string:
        session: str | StringSession = StringSession(config.session_string)
    else:
        session = str(config.session_path)

    client = TelegramClient(
        session,
        config.api_id,
        config.api_hash,
    )
    # Shared bags used by plugins / main
    client._userbot_config = config  # type: ignore[attr-defined]
    client._userbot_bg_tasks = []  # type: ignore[attr-defined]
    client._userbot_help = []  # type: ignore[attr-defined]
    return client
