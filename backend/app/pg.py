"""PostgreSQL connection with the sqlite3 interface the rest of the backend is written against.

The data layer issues plain SQL through ``conn.execute(sql, params)`` with ``?`` placeholders,
``INSERT OR REPLACE`` upserts and ``cursor.lastrowid``. Rather than fork every query, this module
translates those few SQLite idioms to PostgreSQL using the table definitions in ``app.schema``:

    ?                         -> %s   (and literal % -> %%)
    LIKE                      -> ILIKE (SQLite's LIKE is case-insensitive for ASCII)
    INSERT OR REPLACE INTO t  -> INSERT ... ON CONFLICT (pk) DO UPDATE SET col = EXCLUDED.col
    INSERT OR IGNORE INTO t   -> INSERT ... ON CONFLICT DO NOTHING
    INSERT into a serial pk   -> ... RETURNING pk, exposed as cursor.lastrowid
    PRAGMA ...                -> no-op

Rows support both ``row[0]`` and ``row["name"]`` like ``sqlite3.Row``; NUMERIC aggregates come
back as int/float instead of Decimal so JSON output matches SQLite.
"""

from __future__ import annotations

import re
from decimal import Decimal
from functools import lru_cache
from typing import Any, Iterable, Iterator, Sequence

import psycopg

from .schema import metadata

_LITERAL = re.compile(r"('(?:[^']|'')*')")
_INSERT = re.compile(r"^\s*INSERT\s+(OR\s+(REPLACE|IGNORE)\s+)?INTO\s+(\w+)\s*(\(([^)]*)\))?", re.I | re.S)


class Row:
    """Index- and key-addressable row, like sqlite3.Row."""

    __slots__ = ("_keys", "_values", "_index")

    def __init__(self, keys: list[str], index: dict[str, int], values: Sequence[Any]):
        self._keys, self._index, self._values = keys, index, values

    def __getitem__(self, key: int | str) -> Any:
        return self._values[key] if isinstance(key, int) else self._values[self._index[key]]

    def keys(self) -> list[str]:
        return self._keys

    def __iter__(self) -> Iterator[Any]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def _row_factory(cursor: psycopg.Cursor):
    keys = [c.name for c in cursor.description or []]
    index = {k: i for i, k in enumerate(keys)}

    def make(values: Sequence[Any]) -> Row:
        return Row(keys, index, [_plain(v) for v in values])

    return make


def _adapt(params: Iterable[Any] | None) -> list[Any]:
    # SQLite stores booleans as 0/1 in INTEGER columns; PostgreSQL would reject a boolean there.
    return [int(p) if isinstance(p, bool) else p for p in (params or ())]


@lru_cache(maxsize=1024)
def translate(sql: str) -> tuple[str, str | None]:
    """Return (postgres_sql, serial_pk_to_return_or_None)."""
    parts = _LITERAL.split(sql)
    for i in range(0, len(parts), 2):  # outside string literals only
        parts[i] = re.sub(r"\bLIKE\b", "ILIKE", parts[i].replace("%", "%%").replace("?", "%s"), flags=re.I)
    for i in range(1, len(parts), 2):
        parts[i] = parts[i].replace("%", "%%")
    out = "".join(parts).strip().rstrip(";")

    m = _INSERT.match(out)
    if not m:
        return out, None
    mode, table_name, cols = (m.group(2) or "").upper(), m.group(3), m.group(5)
    table = metadata.tables.get(table_name)
    if table is None:
        return out, None
    columns = [c.strip() for c in cols.split(",")] if cols else [c.name for c in table.columns]
    pk = [c.name for c in table.primary_key.columns]
    head = f"INSERT INTO {table_name} ({', '.join(columns)})"
    out = head + out[m.end():]
    if mode == "REPLACE":
        updates = [c for c in columns if c not in pk]
        action = "DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in updates) if updates else "DO NOTHING"
        out += f" ON CONFLICT ({', '.join(pk)}) {action}"
    elif mode == "IGNORE":
        out += " ON CONFLICT DO NOTHING"
    serial = next((c.name for c in table.primary_key.columns if c.autoincrement is True), None)
    if serial and serial not in columns:
        out += f" RETURNING {serial}"
        return out, serial
    return out, None


class Cursor:
    def __init__(self, cur: psycopg.Cursor | None, lastrowid: int | None = None):
        self._cur, self.lastrowid = cur, lastrowid

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount if self._cur else 0

    def fetchone(self) -> Row | None:
        return self._cur.fetchone() if self._cur and self._cur.description else None

    def fetchall(self) -> list[Row]:
        return self._cur.fetchall() if self._cur and self._cur.description else []

    def __iter__(self) -> Iterator[Row]:
        return iter(self.fetchall())


class Connection:
    """The subset of sqlite3.Connection used by the backend."""

    def __init__(self, raw: psycopg.Connection):
        self.raw = raw

    def execute(self, sql: str, params: Iterable[Any] | None = ()) -> Cursor:
        if sql.lstrip().upper().startswith("PRAGMA"):
            return Cursor(None)
        query, serial = translate(sql)
        cur = self.raw.cursor(row_factory=_row_factory)
        cur.execute(query, _adapt(params))
        if serial:
            row = cur.fetchone()
            return Cursor(cur, row[0] if row else None)
        return Cursor(cur)

    def executemany(self, sql: str, seq: Iterable[Iterable[Any]]) -> Cursor:
        query, serial = translate(sql)
        if serial:
            query = query[: query.rfind(" RETURNING ")]
        cur = self.raw.cursor()
        cur.executemany(query, [_adapt(p) for p in seq])
        return Cursor(cur)

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()


def connect(url: str) -> Connection:
    if url.startswith("postgresql+psycopg://"):
        url = "postgresql://" + url.split("://", 1)[1]
    return Connection(psycopg.connect(url))
