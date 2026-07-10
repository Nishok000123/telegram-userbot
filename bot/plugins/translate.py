"""Translate + OCR helpers (optional OpenAI-compatible API)."""

from __future__ import annotations

import base64
import json
import os
import re
from typing import TYPE_CHECKING
from urllib import error, parse, request

from bot.utils.decorators import command, edit_or_reply, register_help
from bot.utils.peers import get_reply_or_fail

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config import Config
    from bot.storage.db import Database


def _http_json(url: str, payload: dict | None = None, headers: dict | None = None) -> dict:
    data = None
    hdrs = {"User-Agent": "telegram-userbot/1.0", "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=hdrs, method="POST" if data else "GET")
    with request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _translate_mymemory(text: str, dest: str) -> str:
    q = parse.urlencode({"q": text[:500], "langpair": f"autodetect|{dest}"})
    url = f"https://api.mymemory.translated.net/get?{q}"
    req = request.Request(url, headers={"User-Agent": "telegram-userbot/1.0"})
    with request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    translated = body.get("responseData", {}).get("translatedText")
    if not translated:
        raise RuntimeError("Translate API returned empty result")
    return translated


def _openai_chat(messages: list[dict], *, image_b64: str | None = None) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    base = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "openrouter/free")
    content: list | str
    if image_b64 is not None:
        # Vision-style content for OCR
        user_text = messages[-1]["content"] if messages else "Extract all text from this image."
        content = [
            {"type": "text", "text": user_text},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
            },
        ]
        payload_messages = [{"role": "user", "content": content}]
    else:
        payload_messages = messages
    result = _http_json(
        f"{base}/chat/completions",
        payload={"model": model, "messages": payload_messages},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return result["choices"][0]["message"]["content"].strip()


def register(client: "TelegramClient", db: "Database", config: "Config") -> None:
    p = config.cmd_prefix
    register_help(
        client,
        "Translate / OCR",
        [
            f"{p}translate [lang] — reply → translate (default en)",
            f"{p}ocr — reply to photo → extract text (needs OPENAI_API_KEY)",
        ],
    )

    @command(client, config, r"translate(?:\s+(\S+))?$")
    async def translate_cmd(event) -> None:
        dest = (event.pattern_match.group(1) or "en").strip().lower()
        if not re.fullmatch(r"[a-z]{2,5}", dest):
            await edit_or_reply(event, f"Usage: `{p}translate en` (reply to text)")
            return
        reply, err = await get_reply_or_fail(event)
        if err or reply is None:
            await edit_or_reply(event, err or "No reply.")
            return
        text = (reply.message or "").strip()
        if not text:
            await edit_or_reply(event, "Replied message has no text.")
            return

        await edit_or_reply(event, "Translating…")
        try:
            if os.getenv("OPENAI_API_KEY", "").strip():
                out = _openai_chat(
                    [
                        {
                            "role": "system",
                            "content": f"Translate to {dest}. Output only the translation.",
                        },
                        {"role": "user", "content": text},
                    ]
                )
            else:
                out = _translate_mymemory(text, dest)
        except error.HTTPError as exc:
            await edit_or_reply(event, f"Translate failed: HTTP {exc.code}")
            return
        except Exception as exc:  # noqa: BLE001
            await edit_or_reply(event, f"Translate failed: {exc}")
            return
        await edit_or_reply(event, f"**→ {dest}**\n{out}")

    @command(client, config, r"ocr$")
    async def ocr_cmd(event) -> None:
        if not os.getenv("OPENAI_API_KEY", "").strip():
            await edit_or_reply(
                event,
                "OCR needs `OPENAI_API_KEY` (OpenRouter free works).\n"
                "Set `OPENAI_BASE_URL` + `OPENAI_MODEL` optional.",
            )
            return
        reply, err = await get_reply_or_fail(event)
        if err or reply is None:
            await edit_or_reply(event, err or "No reply.")
            return
        if not reply.media:
            await edit_or_reply(event, "Reply to a **photo** / image.")
            return

        await edit_or_reply(event, "OCR…")
        path = await reply.download_media(file=str(config.downloads_dir))
        if not path:
            await edit_or_reply(event, "Download failed.")
            return
        with open(path, "rb") as fh:
            raw = fh.read()
        b64 = base64.b64encode(raw).decode("ascii")
        try:
            out = _openai_chat(
                [{"role": "user", "content": "Extract all readable text from this image. Output only the text."}],
                image_b64=b64,
            )
        except Exception as exc:  # noqa: BLE001
            await edit_or_reply(event, f"OCR failed: {exc}")
            return
        await edit_or_reply(event, f"**OCR**\n{out}" if out else "No text found.")
