"""satark.ingest.feeds: the domain-file parser (IP exclusion, comments), the blocklist_domain
merge upsert, and copy_previous_feed's per-feed slice of that shared table."""

from __future__ import annotations

import sqlite3

from satark.ingest.feeds import copy_previous_feed, load_domain_file, merge_into

_PATTERN = r"^[a-z0-9.-]+\.[a-z]{2,}$"


def test_load_domain_file_skips_comments_blanks_and_bare_ips(tmp_path):
    f = tmp_path / "feed.txt"
    f.write_text(
        "# a comment\n"
        "\n"
        "evil-phish.example\n"
        "101.0.81.153\n"
        "0.0.0.0 hosts-style.example\n"
        "::1\n"
        "EVIL-PHISH.EXAMPLE\n"  # same domain, different case -> dedup, not a second row
    )
    result = load_domain_file({"_root": tmp_path, "path": "feed.txt", "gates": {"key_pattern": _PATTERN}})
    assert set(result.rows) == {("evil-phish.example",), ("hosts-style.example",)}
    assert result.total == 3  # the three real domain-line attempts; comments/blanks/IPs never counted
    assert result.matched == 3


def test_load_domain_file_prefers_the_cache_over_the_local_path(tmp_path):
    cache = tmp_path / "cache.txt"
    cache.write_text("cached.example\n")
    local = tmp_path / "local.txt"
    local.write_text("local.example\n")
    result = load_domain_file(
        {"_root": tmp_path, "cache": "cache.txt", "path": "local.txt", "gates": {"key_pattern": _PATTERN}}
    )
    assert result.rows == [("cached.example",)]


def test_load_domain_file_missing_file_is_a_clean_empty_result(tmp_path):
    result = load_domain_file({"_root": tmp_path, "cache": "missing.txt", "gates": {"key_pattern": _PATTERN}})
    assert result.rows == []
    assert result.total == 0
    assert result.matched == 0
    assert result.as_on == ""
    assert result.sha256 is None


def _schema_sql() -> str:
    from satark.ingest.__main__ import SCHEMA

    return SCHEMA.read_text()


def test_merge_into_unions_feeds_without_duplicating_a_feed_id(tmp_path):
    con = sqlite3.connect(tmp_path / "t.db")
    con.executescript(_schema_sql())
    con.execute("INSERT INTO ingest_run (source_id, started_at, status, row_count, as_on) VALUES ('x','t','ok',0,'2026-10-03')")
    run_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]

    merge_into(con, "phishing_database", ["evil.example", "shared.example"], run_id)
    merge_into(con, "hagezi_tif", ["shared.example", "hagezi-only.example"], run_id)
    merge_into(con, "phishing_database", ["shared.example"], run_id)  # re-merging the same feed again

    rows = dict(con.execute("SELECT domain, feeds FROM blocklist_domain").fetchall())
    assert rows["evil.example"] == "phishing_database"
    assert rows["hagezi-only.example"] == "hagezi_tif"
    assert set(rows["shared.example"].split(",")) == {"phishing_database", "hagezi_tif"}  # no duplicate token
    con.close()


def test_copy_previous_feed_carries_only_that_feeds_domains(tmp_path):
    old = sqlite3.connect(tmp_path / "old.db")
    old.executescript(_schema_sql())
    old.execute("INSERT INTO ingest_run (source_id, started_at, status, row_count, as_on) VALUES ('phishing_database','t','ok',2,'2026-10-01')")
    run_a = old.execute("SELECT last_insert_rowid()").fetchone()[0]
    old.execute("INSERT INTO ingest_run (source_id, started_at, status, row_count, as_on) VALUES ('hagezi_tif','t','ok',1,'2026-10-01')")
    run_b = old.execute("SELECT last_insert_rowid()").fetchone()[0]
    old.executemany(
        "INSERT INTO blocklist_domain (domain, feeds, run_id) VALUES (?,?,?)",
        [("shared.example", "phishing_database,hagezi_tif", run_b), ("phish-only.example", "phishing_database", run_a)],
    )
    old.commit()
    old.close()

    con = sqlite3.connect(tmp_path / "next.db")
    con.executescript(_schema_sql())
    con.execute("ATTACH DATABASE ? AS old", (str(tmp_path / "old.db"),))

    copied = copy_previous_feed(con, "phishing_database", "2026-10-04T00:00:00Z")
    assert copied == {"status": "kept_previous", "row_count": 2, "as_on": "2026-10-01"}
    domains = {r[0] for r in con.execute("SELECT domain FROM blocklist_domain").fetchall()}
    assert domains == {"shared.example", "phish-only.example"}  # hagezi's exclusive rows are not copied
    con.close()


def test_copy_previous_feed_with_no_previous_run_returns_none(tmp_path):
    old = sqlite3.connect(tmp_path / "old.db")
    old.executescript(_schema_sql())
    old.close()
    con = sqlite3.connect(tmp_path / "next.db")
    con.executescript(_schema_sql())
    con.execute("ATTACH DATABASE ? AS old", (str(tmp_path / "old.db"),))
    assert copy_previous_feed(con, "phishing_database", "2026-10-04T00:00:00Z") is None
    con.close()
