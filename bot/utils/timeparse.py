"""Parse simple relative times like 10m, 2h, 1d."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_RE = re.compile(
    r"^(?:(\d+)\s*d)?(?:(\d+)\s*h)?(?:(\d+)\s*m)?(?:(\d+)\s*s)?$",
    re.IGNORECASE,
)


def parse_duration(text: str) -> timedelta | None:
    raw = text.strip().lower().replace(" ", "")
    if not raw:
        return None

    # Allow plain forms: 30m, 2h, 1d, 90s, 1h30m
    m = _RE.match(raw)
    if not m or not any(m.groups()):
        return None

    days = int(m.group(1) or 0)
    hours = int(m.group(2) or 0)
    minutes = int(m.group(3) or 0)
    seconds = int(m.group(4) or 0)
    if days + hours + minutes + seconds <= 0:
        return None
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def format_local(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    return local.strftime("%Y-%m-%d %H:%M:%S %Z")
