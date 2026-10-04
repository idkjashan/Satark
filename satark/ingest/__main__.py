"""Build data/registry.db from the raw snapshots in data/manual/ (LLD §16).

    uv run python -m satark.ingest              # offline build from data/manual/
    uv run python -m satark.ingest --fetch       # download threat feeds first, then build
    uv run python -m satark.ingest --only sebi_ia      # rebuild one source; copy the rest as is
    uv run python -m satark.ingest --db /tmp/registry.db

Every source goes through the same gate (satark.ingest.gate.check_gate) before its rows enter
data/registry.next.db; a source that fails keeps its previous rows, copied from the database
being replaced, and is recorded 'kept_previous' -- it never empties a table. The new file is
swapped in with os.replace (atomic on one filesystem) only after FTS5 is rebuilt, ANALYZE has
run and PRAGMA integrity_check says 'ok'.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import yaml

from satark.infra.norm import site_domain
from satark.ingest import crux, curated, feeds, nse, sebi
from satark.ingest.gate import (
    bulk_insert,
    check_gate,
    copy_previous,
    insert_ingest_run,
    previous_run,
    utcnow_iso,
)

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA = ROOT / "satark" / "ingest" / "schema.sql"

# Aggregate id -> the real source ids it summarises (LLD: checkers cite the aggregate's source chip).
AGGREGATES: dict[str, list[str]] = {
    "sebi_registers": [
        "sebi_ia", "sebi_ra", "sebi_broker_equity", "sebi_broker_fo", "sebi_broker_currency",
        "sebi_broker_commodity", "sebi_dp_cdsl", "sebi_dp_nsdl", "sebi_pms", "sebi_mf", "sebi_aif",
        "sebi_mb", "sebi_rta",
    ],
    "blocklists": ["phishing_database", "hagezi_tif", "blocklist_local"],
}

# Real (DB-backed) source id -> the function that loads it. Order doubles as build order.
LOADERS = {
    **dict.fromkeys(AGGREGATES["sebi_registers"], sebi.load),  # all 13 SEBI categories share one loader
    "nse_debarred": nse.load_debarred,
    "nse_broker_apps": nse.load_broker_apps,
    "nse_broker_social": nse.load_broker_social,
    "nse_equity_list": nse.load_equity_list,
    "crux_india": crux.load,
    "official_domains": curated.load_official_domains,
    "caution_lists": curated.load_caution_entries,
    "psp_handles": curated.load_psp_handles,
    "phishing_database": feeds.load_domain_file,
    "hagezi_tif": feeds.load_domain_file,
    "blocklist_local": feeds.load_domain_file,
}

REAL_SOURCE_IDS = list(LOADERS.keys())


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m satark.ingest")
    p.add_argument("--fetch", action="store_true", help="download threat feeds into data/cache/feeds/ first")
    p.add_argument("--only", metavar="SOURCE_ID", help="rebuild one source (or aggregate id); copy the rest from --db")
    p.add_argument("--db", metavar="PATH", help="registry database path (default data/registry.db)")
    return p.parse_args(argv)


def _active_ids(only: str | None) -> set[str]:
    if not only:
        return set(REAL_SOURCE_IDS)
    if only in AGGREGATES:
        return set(AGGREGATES[only])
    if only in LOADERS:
        return {only}
    raise SystemExit(f"unknown --only source id: {only!r}")


def load_one(con: sqlite3.Connection, source_id: str, spec: dict, started_at: str, old_attached: bool) -> dict:
    """Run one source's loader, gate its result, and either commit it or fall back to kept_previous."""
    enriched = {**spec, "_source_id": source_id, "_root": ROOT}
    try:
        result = LOADERS[source_id](enriched)
        error = None
    except Exception as e:  # noqa: BLE001 - a broken/missing input file is a gate failure, not a crash
        result, error = None, f"{type(e).__name__}: {e}"

    prev = previous_run(con, source_id) if old_attached else None
    if result is not None:
        passed, reason = check_gate(
            total=result.total,
            matched=result.matched,
            row_count=len(result.rows),
            min_rows=spec["gates"]["min_rows"],
            max_drop_pct=spec["gates"]["max_drop_pct"],
            as_on=result.as_on,
            prev_row_count=prev["row_count"] if prev else None,
            prev_as_on=prev["as_on"] if prev else None,
            pattern_min_rate=spec["gates"].get("pattern_min_rate"),
        )
    else:
        passed, reason = False, error or "loader raised with no message"

    if passed:
        assert result is not None
        run_id = insert_ingest_run(con, source_id, started_at, "ok", len(result.rows), result.sha256, result.as_on)
        if spec["table"] == "blocklist_domain":
            feeds.merge_into(con, source_id, [r[0] for r in result.rows], run_id)
        else:
            bulk_insert(con, spec["table"], result.rows, run_id)
        return {"status": "ok", "row_count": len(result.rows), "as_on": result.as_on}

    copied = None
    if old_attached:
        if spec["table"] == "blocklist_domain":
            copied = feeds.copy_previous_feed(con, source_id, started_at)
        else:
            copied = copy_previous(con, source_id, spec["table"], started_at, force_status="kept_previous")
    if copied:
        print(f"  {source_id}: kept_previous ({reason})", file=sys.stderr)
        return copied

    as_on = result.as_on if (result and result.as_on) else started_at[:10]
    sha = result.sha256 if result else None
    insert_ingest_run(con, source_id, started_at, "failed", 0, sha, as_on)
    print(f"  {source_id}: failed, no previous rows to keep ({reason})", file=sys.stderr)
    return {"status": "failed", "row_count": 0, "as_on": as_on}


def copy_verbatim(con: sqlite3.Connection, source_id: str, spec: dict, started_at: str) -> dict | None:
    """--only: carry an untouched source's rows and ingest_run row forward unchanged."""
    if spec["table"] == "blocklist_domain":
        return feeds.copy_previous_feed(con, source_id, started_at, force_status=None)
    return copy_previous(con, source_id, spec["table"], started_at, force_status=None)


def write_aggregate(con: sqlite3.Connection, agg_id: str, members: list[dict], started_at: str) -> None:
    statuses = {m["status"] for m in members}
    status = "ok" if statuses == {"ok"} else ("failed" if statuses == {"failed"} else "kept_previous")
    row_count = sum(m["row_count"] for m in members)
    as_on_values = [m["as_on"] for m in members if m["as_on"]]
    as_on = min(as_on_values) if as_on_values else started_at[:10]
    insert_ingest_run(con, agg_id, started_at, status, row_count, None, as_on)


# Threat feeds list whole platforms whose subdomains or paths once hosted phishing (google.com, bit.ly,
# github.io, blogspot.com, even banks' own domains). A blocklist hit is a critical signal, so an entry
# whose registrable domain is an official domain or popular in India (CrUX top 50,000) never counts.
POPULAR_BUCKET = 50_000


def prune_blocklist(con: sqlite3.Connection) -> int:
    keep_out = {r[0] for r in con.execute("SELECT domain FROM official_domain")}
    keep_out |= {r[0] for r in con.execute("SELECT domain FROM popularity WHERE crux_bucket <= ?", (POPULAR_BUCKET,))}
    doomed = [(d,) for (d,) in con.execute("SELECT domain FROM blocklist_domain")
              if d in keep_out or site_domain(d) in keep_out]
    con.executemany("DELETE FROM blocklist_domain WHERE domain = ?", doomed)
    return len(doomed)


def build(db_path: Path, fetch_first: bool, only: str | None) -> dict[str, dict]:
    if only and not db_path.exists():
        raise SystemExit(f"--only {only!r} needs an existing database at {db_path} to copy the other sources from")

    sources_cfg = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text())

    if fetch_first:
        print("fetching threat feeds...", file=sys.stderr)
        for sid, st in feeds.fetch(ROOT, sources_cfg).items():
            print(f"  {sid}: {st}", file=sys.stderr)

    next_path = db_path.with_name(db_path.stem + ".next" + db_path.suffix)
    next_path.unlink(missing_ok=True)
    next_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(next_path)
    con.executescript(SCHEMA.read_text())

    old_attached = db_path.exists()
    if old_attached:
        con.execute("ATTACH DATABASE ? AS old", (str(db_path),))

    started_at = utcnow_iso()
    active = _active_ids(only)
    results: dict[str, dict] = {}

    for source_id in REAL_SOURCE_IDS:
        spec = sources_cfg[source_id]
        if source_id in active:
            results[source_id] = load_one(con, source_id, spec, started_at, old_attached)
        else:
            copied = copy_verbatim(con, source_id, spec, started_at) if old_attached else None
            if copied is None:  # should not happen (guarded above), but never silently empty a table
                insert_ingest_run(con, source_id, started_at, "failed", 0, None, started_at[:10])
                copied = {"status": "failed", "row_count": 0, "as_on": started_at[:10]}
            results[source_id] = copied

    for agg_id, members in AGGREGATES.items():
        write_aggregate(con, agg_id, [results[m] for m in members], started_at)

    if old_attached:
        con.commit()  # SQLite refuses to DETACH a database touched by an open transaction
        con.execute("DETACH DATABASE old")

    pruned = prune_blocklist(con)
    if pruned:
        print(f"blocklist: dropped {pruned} entries that are official or popular platforms", file=sys.stderr)
    con.execute("INSERT INTO intermediary_fts (intermediary_fts) VALUES ('rebuild')")
    con.execute("ANALYZE")
    (integrity,) = con.execute("PRAGMA integrity_check").fetchone()
    if integrity != "ok":
        con.close()
        next_path.unlink(missing_ok=True)
        raise RuntimeError(f"PRAGMA integrity_check failed: {integrity}")

    prev_version = 0
    if db_path.exists():
        old_con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        row = old_con.execute("SELECT value FROM meta WHERE key = 'data_version'").fetchone()
        prev_version = int(row[0]) if row else 0
        old_con.close()
    con.executemany(
        "INSERT INTO meta (key, value) VALUES (?, ?)",
        [("data_version", str(prev_version + 1)), ("built_at", utcnow_iso())],
    )
    con.commit()
    con.close()

    os.replace(next_path, db_path)
    return results


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    db_path = Path(args.db) if args.db else ROOT / "data" / "registry.db"
    results = build(db_path, fetch_first=args.fetch, only=args.only)
    for source_id in sorted(results):
        r = results[source_id]
        print(f"{source_id}: {r['status']} rows={r['row_count']} as_on={r['as_on']}")


if __name__ == "__main__":
    main()
