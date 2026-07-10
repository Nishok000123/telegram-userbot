"""SQLite storage helpers."""

from __future__ import annotations

import aiosqlite
from pathlib import Path
from typing import Any


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.execute("PRAGMA foreign_keys=ON;")

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database is not connected")
        return self._db

    async def init_schema(self) -> None:
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        await self.db.executescript(sql)
        await self.db.commit()

    # ---- settings ----

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        cur = await self.db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cur.fetchone()
        return row["value"] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        await self.db.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self.db.commit()

    async def delete_setting(self, key: str) -> None:
        await self.db.execute("DELETE FROM settings WHERE key = ?", (key,))
        await self.db.commit()

    # ---- notes ----

    async def upsert_note(self, name: str, content: str, updated_at: str) -> None:
        await self.db.execute(
            "INSERT INTO notes(name, content, updated_at) VALUES(?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET content = excluded.content, "
            "updated_at = excluded.updated_at",
            (name, content, updated_at),
        )
        await self.db.commit()

    async def get_note(self, name: str) -> str | None:
        cur = await self.db.execute("SELECT content FROM notes WHERE name = ?", (name,))
        row = await cur.fetchone()
        return row["content"] if row else None

    async def list_notes(self) -> list[str]:
        cur = await self.db.execute("SELECT name FROM notes ORDER BY name COLLATE NOCASE")
        rows = await cur.fetchall()
        return [r["name"] for r in rows]

    async def delete_note(self, name: str) -> bool:
        cur = await self.db.execute("DELETE FROM notes WHERE name = ?", (name,))
        await self.db.commit()
        return cur.rowcount > 0

    # ---- snippets ----

    async def upsert_snippet(self, name: str, content: str, updated_at: str) -> None:
        await self.db.execute(
            "INSERT INTO snippets(name, content, updated_at) VALUES(?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET content = excluded.content, "
            "updated_at = excluded.updated_at",
            (name, content, updated_at),
        )
        await self.db.commit()

    async def get_snippet(self, name: str) -> str | None:
        cur = await self.db.execute("SELECT content FROM snippets WHERE name = ?", (name,))
        row = await cur.fetchone()
        return row["content"] if row else None

    async def list_snippets(self) -> list[str]:
        cur = await self.db.execute("SELECT name FROM snippets ORDER BY name COLLATE NOCASE")
        rows = await cur.fetchall()
        return [r["name"] for r in rows]

    async def delete_snippet(self, name: str) -> bool:
        cur = await self.db.execute("DELETE FROM snippets WHERE name = ?", (name,))
        await self.db.commit()
        return cur.rowcount > 0

    # ---- reminders ----

    async def add_reminder(
        self, due_at: str, text: str, chat_id: int, created_at: str
    ) -> int:
        cur = await self.db.execute(
            "INSERT INTO reminders(due_at, text, chat_id, created_at, done) "
            "VALUES(?, ?, ?, ?, 0)",
            (due_at, text, chat_id, created_at),
        )
        await self.db.commit()
        return int(cur.lastrowid)

    async def list_reminders(self, include_done: bool = False) -> list[dict[str, Any]]:
        if include_done:
            cur = await self.db.execute(
                "SELECT id, due_at, text, chat_id, created_at, done "
                "FROM reminders ORDER BY due_at"
            )
        else:
            cur = await self.db.execute(
                "SELECT id, due_at, text, chat_id, created_at, done "
                "FROM reminders WHERE done = 0 ORDER BY due_at"
            )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def due_reminders(self, now_iso: str) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            "SELECT id, due_at, text, chat_id, created_at, done "
            "FROM reminders WHERE done = 0 AND due_at <= ? ORDER BY due_at",
            (now_iso,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def mark_reminder_done(self, reminder_id: int) -> None:
        await self.db.execute(
            "UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,)
        )
        await self.db.commit()

    async def delete_reminder(self, reminder_id: int) -> bool:
        cur = await self.db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        await self.db.commit()
        return cur.rowcount > 0

    # ---- downloads ----

    async def log_download(self, path: str, source: str | None, created_at: str) -> None:
        await self.db.execute(
            "INSERT INTO download_log(path, source, created_at) VALUES(?, ?, ?)",
            (path, source, created_at),
        )
        await self.db.commit()
