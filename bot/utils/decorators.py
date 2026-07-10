"""Command helpers: self-only outgoing commands + help registry."""

from __future__ import annotations

import functools
import re
from typing import Any, Awaitable, Callable, TYPE_CHECKING

from telethon import events

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config

Handler = Callable[..., Awaitable[Any]]


def register_help(client: "TelegramClient", section: str, lines: list[str]) -> None:
    help_list: list[tuple[str, list[str]]] = getattr(client, "_userbot_help", [])
    help_list.append((section, lines))
    client._userbot_help = help_list  # type: ignore[attr-defined]


def command(
    client: "TelegramClient",
    config: "Config",
    pattern: str,
    *,
    flags: int = re.IGNORECASE,
) -> Callable[[Handler], Handler]:
    """Register a handler for outgoing messages from you that match the pattern.

    `pattern` is the part after the prefix, e.g. r"ping$" or r"note(?: |$)(.*)".
    """

    prefix = re.escape(config.cmd_prefix)
    compiled = re.compile(rf"^{prefix}{pattern}", flags)

    def decorator(func: Handler) -> Handler:
        @client.on(events.NewMessage(outgoing=True, pattern=compiled))
        @functools.wraps(func)
        async def wrapper(event: events.NewMessage.Event) -> None:
            await func(event)

        return func

    return decorator


async def edit_or_reply(event: events.NewMessage.Event, text: str) -> None:
    """Prefer editing the command message; fall back to a reply."""
    try:
        await event.edit(text)
    except Exception:
        await event.reply(text)
