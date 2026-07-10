"""DB backends: local aiosqlite or remote Turso (libsql)."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Iterable, Sequence


def _as_dict_row(columns: Sequence[str], values: Sequence[Any]) -> dict[str, Any]:
    return {columns[i]: values[i] for i in range(len(columns))}


class _CursorResult:
    """Minimal async cursor compatible with our Database helpers."""

    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        rowcount: int = -1,
        lastrowid: int | None = None,
    ) -> None:
        self._rows = rows
        self._i = 0
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    async def fetchone(self) -> dict[str, Any] | None:
        if self._i >= len(self._rows):
            return None
        row = self._rows[self._i]
        self._i += 1
        return row

    async def fetchall(self) -> list[dict[str, Any]]:
        rest = self._rows[self._i :]
        self._i = len(self._rows)
        return rest


class LocalAioSqlite:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._db: Any = None

    async def connect(self) -> None:
        import aiosqlite

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.execute("PRAGMA foreign_keys=ON;")

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> _CursorResult:
        assert self._db is not None
        cur = await self._db.execute(sql, tuple(params))
        raw = await cur.fetchall()
        rows = [dict(r) for r in raw]
        return _CursorResult(
            rows,
            rowcount=cur.rowcount if cur.rowcount is not None else -1,
            lastrowid=cur.lastrowid,
        )

    async def executescript(self, sql: str) -> None:
        assert self._db is not None
        await self._db.executescript(sql)

    async def commit(self) -> None:
        assert self._db is not None
        await self._db.commit()


class TursoLibsql:
    """Remote Turso via sync `libsql`, wrapped for asyncio."""

    def __init__(self, url: str, auth_token: str) -> None:
        self.url = url
        self.auth_token = auth_token
        self._conn: Any = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        import libsql

        def _open() -> Any:
            return libsql.connect(database=self.url, auth_token=self.auth_token)

        self._conn = await asyncio.to_thread(_open)

    async def close(self) -> None:
        if self._conn is None:
            return

        def _close() -> None:
            self._conn.close()

        async with self._lock:
            await asyncio.to_thread(_close)
            self._conn = None

    def _execute_sync(self, sql: str, params: tuple[Any, ...]) -> _CursorResult:
        assert self._conn is not None
        cur = self._conn.execute(sql, params)
        columns = [d[0] for d in (cur.description or [])]
        fetched = cur.fetchall() if columns else []
        rows = [_as_dict_row(columns, row) for row in fetched]
        lastrowid = getattr(cur, "lastrowid", None)
        rowcount = getattr(cur, "rowcount", -1)
        return _CursorResult(rows, rowcount=rowcount, lastrowid=lastrowid)

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> _CursorResult:
        async with self._lock:
            return await asyncio.to_thread(self._execute_sync, sql, tuple(params))

    async def executescript(self, sql: str) -> None:
        # Split on semicolons; skip empty / comment-only chunks
        parts = [p.strip() for p in re.split(r";\s*\n", sql) if p.strip()]
        async with self._lock:
            for part in parts:
                cleaned = "\n".join(
                    line
                    for line in part.splitlines()
                    if line.strip() and not line.strip().startswith("--")
                ).strip()
                if not cleaned:
                    continue
                await asyncio.to_thread(self._conn.execute, cleaned)
                await asyncio.to_thread(self._conn.commit)

    async def commit(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._conn.commit)
