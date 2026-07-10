"""SQLite / Turso storage helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bot.storage.backend import LocalAioSqlite, TursoLibsql

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class Database:
    def __init__(
        self,
        path: Path,
        *,
        turso_url: str | None = None,
        turso_token: str | None = None,
    ) -> None:
        self.path = path
        self.turso_url = (turso_url or "").strip() or None
        self.turso_token = (turso_token or "").strip() or None
        self._backend: LocalAioSqlite | TursoLibsql | None = None

    @property
    def using_turso(self) -> bool:
        return bool(self.turso_url and self.turso_token)

    async def connect(self) -> None:
        if self.using_turso:
            assert self.turso_url and self.turso_token
            self._backend = TursoLibsql(self.turso_url, self.turso_token)
        else:
            self._backend = LocalAioSqlite(self.path)
        await self._backend.connect()

    async def close(self) -> None:
        if self._backend is not None:
            await self._backend.close()
            self._backend = None

    @property
    def db(self) -> LocalAioSqlite | TursoLibsql:
        if self._backend is None:
            raise RuntimeError("Database is not connected")
        return self._backend

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
        cur = await self.db.execute(
            "SELECT name FROM notes ORDER BY name COLLATE NOCASE"
        )
        rows = await cur.fetchall()
        return [r["name"] for r in rows]

    async def delete_note(self, name: str) -> bool:
        cur = await self.db.execute("DELETE FROM notes WHERE name = ?", (name,))
        await self.db.commit()
        return (cur.rowcount or 0) > 0

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
        cur = await self.db.execute(
            "SELECT content FROM snippets WHERE name = ?", (name,)
        )
        row = await cur.fetchone()
        return row["content"] if row else None

    async def list_snippets(self) -> list[str]:
        cur = await self.db.execute(
            "SELECT name FROM snippets ORDER BY name COLLATE NOCASE"
        )
        rows = await cur.fetchall()
        return [r["name"] for r in rows]

    async def delete_snippet(self, name: str) -> bool:
        cur = await self.db.execute("DELETE FROM snippets WHERE name = ?", (name,))
        await self.db.commit()
        return (cur.rowcount or 0) > 0

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
        return int(cur.lastrowid or 0)

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
        return await cur.fetchall()

    async def due_reminders(self, now_iso: str) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            "SELECT id, due_at, text, chat_id, created_at, done "
            "FROM reminders WHERE done = 0 AND due_at <= ? ORDER BY due_at",
            (now_iso,),
        )
        return await cur.fetchall()

    async def mark_reminder_done(self, reminder_id: int) -> None:
        await self.db.execute(
            "UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,)
        )
        await self.db.commit()

    async def delete_reminder(self, reminder_id: int) -> bool:
        cur = await self.db.execute(
            "DELETE FROM reminders WHERE id = ?", (reminder_id,)
        )
        await self.db.commit()
        return (cur.rowcount or 0) > 0

    # ---- downloads ----

    async def log_download(self, path: str, source: str | None, created_at: str) -> None:
        await self.db.execute(
            "INSERT INTO download_log(path, source, created_at) VALUES(?, ?, ?)",
            (path, source, created_at),
        )
        await self.db.commit()

    # ---- tags ----

    async def upsert_tag(
        self,
        user_id: int,
        label: str,
        note: str | None,
        display_name: str | None,
        username: str | None,
        updated_at: str,
    ) -> None:
        await self.db.execute(
            "INSERT INTO tags(user_id, label, note, display_name, username, updated_at) "
            "VALUES(?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, label) DO UPDATE SET "
            "note = excluded.note, "
            "display_name = excluded.display_name, "
            "username = excluded.username, "
            "updated_at = excluded.updated_at",
            (user_id, label, note, display_name, username, updated_at),
        )
        await self.db.commit()

    async def get_tags_for_user(self, user_id: int) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            "SELECT user_id, label, note, display_name, username, updated_at "
            "FROM tags WHERE user_id = ? ORDER BY label COLLATE NOCASE",
            (user_id,),
        )
        return await cur.fetchall()

    async def list_all_tags(self) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            "SELECT user_id, label, note, display_name, username, updated_at "
            "FROM tags ORDER BY label COLLATE NOCASE, display_name COLLATE NOCASE"
        )
        return await cur.fetchall()

    async def list_users_by_label(self, label: str) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            "SELECT user_id, label, note, display_name, username, updated_at "
            "FROM tags WHERE label = ? COLLATE NOCASE "
            "ORDER BY display_name COLLATE NOCASE",
            (label,),
        )
        return await cur.fetchall()

    async def delete_tag(self, user_id: int, label: str) -> bool:
        cur = await self.db.execute(
            "DELETE FROM tags WHERE user_id = ? AND label = ? COLLATE NOCASE",
            (user_id, label),
        )
        await self.db.commit()
        return (cur.rowcount or 0) > 0

    async def clear_tags(self, user_id: int) -> int:
        cur = await self.db.execute("DELETE FROM tags WHERE user_id = ?", (user_id,))
        await self.db.commit()
        return max(cur.rowcount or 0, 0)

    # ---- filters ----

    async def upsert_filter(self, keyword: str, response: str, updated_at: str) -> None:
        await self.db.execute(
            "INSERT INTO filters(keyword, response, updated_at) VALUES(?, ?, ?) "
            "ON CONFLICT(keyword) DO UPDATE SET response = excluded.response, "
            "updated_at = excluded.updated_at",
            (keyword, response, updated_at),
        )
        await self.db.commit()

    async def get_filter(self, keyword: str) -> str | None:
        cur = await self.db.execute(
            "SELECT response FROM filters WHERE keyword = ? COLLATE NOCASE",
            (keyword,),
        )
        row = await cur.fetchone()
        return row["response"] if row else None

    async def list_filters(self) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            "SELECT keyword, response, updated_at FROM filters "
            "ORDER BY keyword COLLATE NOCASE"
        )
        return await cur.fetchall()

    async def delete_filter(self, keyword: str) -> bool:
        cur = await self.db.execute(
            "DELETE FROM filters WHERE keyword = ? COLLATE NOCASE", (keyword,)
        )
        await self.db.commit()
        return (cur.rowcount or 0) > 0

    async def match_filters(self, text: str) -> list[dict[str, Any]]:
        rows = await self.list_filters()
        lowered = text.lower()
        return [r for r in rows if r["keyword"].lower() in lowered]

    # ---- locks ----

    async def upsert_lock(
        self,
        user_id: int,
        display_name: str | None,
        username: str | None,
        reason: str | None,
        created_at: str,
    ) -> None:
        await self.db.execute(
            "INSERT INTO locks(user_id, display_name, username, reason, created_at) "
            "VALUES(?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "display_name = excluded.display_name, "
            "username = excluded.username, "
            "reason = excluded.reason",
            (user_id, display_name, username, reason, created_at),
        )
        await self.db.commit()

    async def is_locked(self, user_id: int) -> bool:
        cur = await self.db.execute(
            "SELECT 1 AS ok FROM locks WHERE user_id = ?", (user_id,)
        )
        return await cur.fetchone() is not None

    async def list_locks(self) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            "SELECT user_id, display_name, username, reason, created_at "
            "FROM locks ORDER BY created_at DESC"
        )
        return await cur.fetchall()

    async def delete_lock(self, user_id: int) -> bool:
        cur = await self.db.execute("DELETE FROM locks WHERE user_id = ?", (user_id,))
        await self.db.commit()
        return (cur.rowcount or 0) > 0

    # ---- export ----

    async def export_bundle(self) -> dict[str, Any]:
        cur = await self.db.execute(
            "SELECT name, content, updated_at FROM notes ORDER BY name COLLATE NOCASE"
        )
        notes = await cur.fetchall()
        cur = await self.db.execute(
            "SELECT name, content, updated_at FROM snippets ORDER BY name COLLATE NOCASE"
        )
        snips = await cur.fetchall()
        return {
            "notes": notes,
            "snippets": snips,
            "tags": await self.list_all_tags(),
            "filters": await self.list_filters(),
            "locks": await self.list_locks(),
            "reminders": await self.list_reminders(include_done=False),
        }
