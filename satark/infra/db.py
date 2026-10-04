"""Read-only access to the registry database built by `python -m satark.ingest` (LLD §14.1)."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any


class RegistryDB:
    """One read-only SQLite connection. Lookups take well under 1 ms and run inline on the event loop.

    note: one shared connection behind a lock; use a connection per thread if p99 query time grows.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"registry database not found: {self.path}")
        self._conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self.data_version = int(self.meta("data_version") or 0)
        self.built_at = self.meta("built_at")

    def query(self, sql: str, params: tuple[Any, ...] | dict[str, Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple[Any, ...] | dict[str, Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def meta(self, key: str) -> str | None:
        row = self.one("SELECT value FROM meta WHERE key = ?", (key,))
        return row["value"] if row else None

    def source_as_on(self, source_id: str) -> str | None:
        """The `as_on` date of the latest successful load of a source (for source chips and staleness)."""
        row = self.one(
            "SELECT as_on FROM ingest_run WHERE source_id = ? AND status IN ('ok', 'kept_previous') "
            "ORDER BY id DESC LIMIT 1",
            (source_id,),
        )
        return row["as_on"] if row else None

    def sources(self) -> list[dict[str, Any]]:
        """Latest run per source, for /v1/meta."""
        rows = self.query(
            "SELECT source_id, status, as_on, row_count FROM ingest_run WHERE id IN "
            "(SELECT MAX(id) FROM ingest_run GROUP BY source_id) ORDER BY source_id"
        )
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
