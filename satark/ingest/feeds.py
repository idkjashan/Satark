"""Threat-intelligence feeds -> blocklist_domain (LLD §15.2, §16).

`--fetch` downloads the two public feeds into data/cache/feeds/; the parse/merge step here runs
either way. A feed with no cached file yet (never fetched, or the fetch failed) reports zero
rows for this build, and the driver's gate falls back to kept_previous (or 'failed' with nothing
to keep, on a first-ever offline build) -- the build never blocks on the network.

blocklist_domain is a merge table: several feeds can list the same domain, so a row's `feeds`
column is a de-duplicated, comma-joined union rather than one row per feed. That makes "keep this
one feed's previous rows" a different operation from the generic satark.ingest.gate.copy_previous
(which assumes one run owns a row outright), hence copy_previous_feed below.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Connection

from satark.infra.norm import registrable_domain
from satark.ingest.gate import SourceResult, insert_ingest_run, previous_run, sha256_file

_COMMENT = re.compile(r"^\s*#")
_IP = re.compile(r"^\d{1,3}(\.\d{1,3}){3}(:\d+)?$|^[0-9a-f:]+:[0-9a-f:]*$", re.IGNORECASE)


def _domains_from_file(path: Path) -> list[str]:
    out = []
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or _COMMENT.match(line):
                continue
            # tolerate stray "0.0.0.0 domain" hosts-file-style lines alongside plain domains
            out.append(line.split()[-1] if " " in line else line)
    return out


def load_domain_file(spec: dict) -> SourceResult:
    """One feed (cached download) or the local additions file -> deduplicated domain list."""
    root = Path(spec["_root"])
    cache = root / spec["cache"] if "cache" in spec else None
    local = root / spec["path"] if "path" in spec else None
    path = cache if (cache and cache.exists()) else local
    if path is None or not path.exists():
        return SourceResult(rows=[], total=0, matched=0, as_on="", sha256=None)

    pattern = re.compile(spec["gates"]["key_pattern"])
    seen: set[str] = set()
    total = matched = 0
    for token in _domains_from_file(path):
        if _IP.match(token):
            continue  # some feeds mix in bare IPs; blocklist_domain is domains only, not an IOC list
        total += 1
        domain = registrable_domain(token)
        if not domain or not pattern.match(domain):
            continue
        matched += 1
        seen.add(domain)

    as_on = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).date().isoformat()
    return SourceResult(rows=[(d,) for d in seen], total=total, matched=matched, as_on=as_on, sha256=sha256_file(path))


def merge_into(con: Connection, source_id: str, domains: list[str], run_id: int) -> None:
    """Upsert (domain, feed_id) pairs into blocklist_domain, unioning `feeds` without duplicates."""
    con.executemany(
        "INSERT INTO blocklist_domain (domain, feeds, run_id) VALUES (?, ?, ?) "
        "ON CONFLICT(domain) DO UPDATE SET "
        "feeds = CASE WHEN instr(',' || feeds || ',', ',' || excluded.feeds || ',') > 0 "
        "THEN feeds ELSE feeds || ',' || excluded.feeds END, "
        "run_id = excluded.run_id",
        [(d, source_id, run_id) for d in domains],
    )


def copy_previous_feed(
    con: Connection, source_id: str, started_at: str, force_status: str | None = "kept_previous"
) -> dict | None:
    """Like gate.copy_previous, but for one feed's slice of the shared blocklist_domain table."""
    prev = previous_run(con, source_id)
    if prev is None:
        return None
    status = force_status or prev["status"]
    new_run_id = insert_ingest_run(con, source_id, started_at, status, prev["row_count"], prev["sha256"], prev["as_on"])
    rows = con.execute(
        "SELECT domain FROM old.blocklist_domain WHERE instr(',' || feeds || ',', ',' || ? || ',') > 0",
        (source_id,),
    ).fetchall()
    merge_into(con, source_id, [r[0] for r in rows], new_run_id)
    return {"status": status, "row_count": prev["row_count"], "as_on": prev["as_on"]}


def fetch(root: Path, sources_cfg: dict) -> dict[str, str]:
    """Download the feeds that have a url into their configured cache path. Best effort: a
    failed download just leaves the previous cache file (if any) in place for the build to use."""
    import httpx

    status: dict[str, str] = {}
    for source_id in ("phishing_database", "hagezi_tif"):
        spec = sources_cfg[source_id]
        dest = root / spec["cache"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        urls = [spec["url"], *([spec["url_fallback"]] if spec.get("url_fallback") else [])]
        ok = False
        for url in urls:
            try:
                with httpx.stream("GET", url, timeout=30.0, follow_redirects=True) as r:
                    if r.status_code != 200:
                        continue
                    tmp = dest.with_suffix(dest.suffix + ".part")
                    with tmp.open("wb") as f:
                        for chunk in r.iter_bytes():
                            f.write(chunk)
                    tmp.replace(dest)
                ok = True
                break
            except httpx.HTTPError:
                continue
        status[source_id] = "fetched" if ok else "fetch_failed"
    return status
