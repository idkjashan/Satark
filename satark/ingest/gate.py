"""Shared gate logic and SQLite helpers for the ingest job (LLD §16).

Every source goes through the same checks before its rows enter data/registry.next.db: its
mapped columns are present (enforced by each loader's own parser -- there is nothing generic to
check once the loader returns clean tuples), its key column matches its pattern for >= 99% of
rows, the row count clears `min_rows` and has not dropped more than `max_drop_pct` versus the
last good run, and `as_on` is not older than the last good run's. A source that fails any of this
keeps its previous rows (status 'kept_previous') instead of emptying its table.

`check_gate` takes plain numbers so it can be unit-tested with no files or database involved.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

PATTERN_MIN_RATE = 0.99  # LLD §16 gate 2: fixed, not per-source configurable


def utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(*paths: Path) -> str:
    """SHA-256 over one or more files, concatenated in the order given."""
    h = hashlib.sha256()
    for p in paths:
        h.update(Path(p).read_bytes())
    return h.hexdigest()


class SourceResult(NamedTuple):
    """What a source loader hands back to the driver."""

    rows: list[tuple]  # ready for INSERT into `table` (TABLE_COLS[table] order), no run_id
    total: int  # input rows/records seen (excluding ones that legitimately carry no data, e.g. "NA")
    matched: int  # of `total`, how many passed the key-pattern + required-field check
    as_on: str  # ISO date this data represents ("" if unknown, e.g. an unfetched feed)
    sha256: str | None


def check_gate(
    *,
    total: int,
    matched: int,
    row_count: int,
    min_rows: int,
    max_drop_pct: float,
    as_on: str,
    prev_row_count: int | None,
    prev_as_on: str | None,
    pattern_min_rate: float | None = None,
) -> tuple[bool, str]:
    """LLD §16 gates 2-5. Returns (passed, reason) -- reason is "" when passed.

    `total`/`matched` are input-row counts, used only for the key-pattern-match-rate gate.
    `row_count` is the number of rows that will actually be inserted (what ends up in
    ingest_run.row_count): for a source where one input row can fan out into several table rows
    (e.g. one broker_social.json record -> several social_handle rows), this is *not* the same
    number as `matched`, and min_rows/max_drop_pct must compare like with like against the
    previous run's row_count rather than against this run's input-row count.
    """
    floor = PATTERN_MIN_RATE if pattern_min_rate is None else pattern_min_rate
    if total > 0:
        rate = matched / total
        if rate < floor:
            return False, f"key pattern matched {rate:.1%} of {total} rows, need >= {floor:.0%}"
    if row_count < min_rows:
        return False, f"{row_count} rows < min_rows {min_rows}"
    if prev_row_count:
        drop_pct = 100 * (prev_row_count - row_count) / prev_row_count
        if drop_pct > max_drop_pct:
            return False, f"row count dropped {drop_pct:.1f}% vs previous run (max {max_drop_pct}%)"
    if prev_as_on and as_on and as_on < prev_as_on:
        return False, f"as_on {as_on} is older than the previous good run's {prev_as_on}"
    return True, ""


# Insert column order per table, matching schema.sql exactly (run_id is appended by bulk_insert).
TABLE_COLS: dict[str, tuple[str, ...]] = {
    "intermediary": (
        "reg_no", "category", "name", "name_norm", "trade_name", "exchange", "valid_from", "valid_to",
        "source_id",
    ),
    "caution_entry": ("list_id", "entry_type", "value_norm", "display", "published_at", "source_url"),
    "official_domain": ("domain", "entity_name", "category", "brand_id"),
    "app_registry": ("package_id", "app_name", "member_name", "developer", "source_list"),
    "social_handle": ("platform", "handle_norm", "entity_name", "entity_kind"),
    "debarred": ("name", "name_norm", "pan_sha256", "order_date", "order_ref", "period", "revoked"),
    "popularity": ("domain", "crux_bucket"),
    "psp_handle": ("handle", "bank", "app"),
    "listed_security": ("symbol", "name", "name_norm", "isin"),
}


def insert_ingest_run(
    con: sqlite3.Connection,
    source_id: str,
    started_at: str,
    status: str,
    row_count: int,
    sha256: str | None,
    as_on: str,
) -> int:
    cur = con.execute(
        "INSERT INTO ingest_run (source_id, started_at, finished_at, status, row_count, sha256, as_on) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (source_id, started_at, utcnow_iso(), status, row_count, sha256, as_on),
    )
    return cur.lastrowid  # type: ignore[return-value]


def bulk_insert(con: sqlite3.Connection, table: str, rows: list[tuple], run_id: int) -> None:
    cols = TABLE_COLS[table]
    placeholders = ",".join("?" * (len(cols) + 1))
    con.executemany(
        f"INSERT INTO {table} ({','.join(cols)}, run_id) VALUES ({placeholders})",
        [(*r, run_id) for r in rows],
    )


def previous_run(con: sqlite3.Connection, source_id: str) -> dict[str, Any] | None:
    """The latest ok/kept_previous run for source_id in the ATTACHed 'old' database, or None."""
    row = con.execute(
        "SELECT id, status, row_count, sha256, as_on FROM old.ingest_run "
        "WHERE source_id = ? AND status IN ('ok', 'kept_previous') ORDER BY id DESC LIMIT 1",
        (source_id,),
    ).fetchone()
    if row is None:
        return None
    return {"run_id": row[0], "status": row[1], "row_count": row[2], "sha256": row[3], "as_on": row[4]}


def copy_previous(
    con: sqlite3.Connection, source_id: str, table: str, started_at: str, force_status: str | None = None
) -> dict[str, Any] | None:
    """Copy source_id's rows from the ATTACHed 'old' db into `table`, with a new ingest_run row.

    Returns the new run's summary, or None if 'old' holds no good run for source_id to copy.
    `force_status`, when given, overrides the carried-forward status (used for a gate failure,
    which must be recorded 'kept_previous' regardless of what the previous run's status was).
    """
    prev = previous_run(con, source_id)
    if prev is None:
        return None
    status = force_status or prev["status"]
    new_run_id = insert_ingest_run(con, source_id, started_at, status, prev["row_count"], prev["sha256"], prev["as_on"])
    cols = ",".join(TABLE_COLS[table])
    con.execute(
        f"INSERT INTO {table} ({cols}, run_id) SELECT {cols}, ? FROM old.{table} WHERE run_id = ?",
        (new_run_id, prev["run_id"]),
    )
    return {"status": status, "row_count": prev["row_count"], "as_on": prev["as_on"]}
