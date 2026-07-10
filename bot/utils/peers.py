"""Peer / message helpers for personal commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from telethon.tl.types import Channel, Chat, User

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.custom.message import Message


def display_user(user: User) -> str:
    parts = [user.first_name or "", user.last_name or ""]
    return " ".join(p for p in parts if p).strip() or "Unknown"


async def resolve_user(
    client: "TelegramClient", event, tokens: list[str]
) -> tuple[User | None, list[str], str | None]:
    """Resolve target user from reply, @username/id, or private peer.

    Returns (user, remaining_tokens, error).
    """
    if event.is_reply:
        reply = await event.get_reply_message()
        sender = await reply.get_sender()
        if isinstance(sender, User):
            return sender, tokens, None
        return None, tokens, "Reply to a **user** message (not a channel)."

    if tokens:
        first = tokens[0]
        if first.startswith("@") or first.lstrip("-").isdigit():
            try:
                entity = await client.get_entity(first)
            except Exception:
                return None, tokens, f"Cannot find user `{first}`."
            if isinstance(entity, User):
                return entity, tokens[1:], None
            return None, tokens, f"`{first}` is not a user."

    if event.is_private:
        chat = await event.get_chat()
        if isinstance(chat, User) and not chat.is_self:
            return chat, tokens, None

    return (
        None,
        tokens,
        "Target a user: reply to them, use `@username`, or run in their DM.",
    )


def message_permalink(chat, chat_id: int, msg_id: int) -> str:
    """Best-effort deep link to a message."""
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}/{msg_id}"

    s = str(chat_id)
    if s.startswith("-100"):
        return f"https://t.me/c/{s[4:]}/{msg_id}"

    if isinstance(chat, User) or chat_id > 0:
        return f"tg://openmessage?user_id={abs(chat_id)}&message_id={msg_id}"

    return f"(chat `{chat_id}` msg `{msg_id}`)"


async def get_reply_or_fail(event) -> tuple["Message" | None, str | None]:
    if not event.is_reply:
        return None, "Reply to a message first."
    reply = await event.get_reply_message()
    if reply is None:
        return None, "Could not load replied message."
    return reply, None
