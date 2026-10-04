"""The ingest driver (satark/ingest/__main__.py): gate -> commit/kept_previous -> aggregate ->
atomic swap, plus one real, slower end-to-end build from the actual data/manual/ tree.

The fake-loader tests substitute tiny in-memory loaders for a couple of real source ids so the
orchestration logic (the part most likely to have a bug) is exercised in milliseconds, without
re-parsing real SEBI/NSE files -- that is already covered by test_ingest_sebi.py / test_ingest_nse.py.
"""

from __future__ import annotations

import re

import pytest

import satark.ingest.__main__ as ingest_main
from satark.infra.db import RegistryDB
from satark.ingest.gate import SourceResult

# config/sources.yaml's real gates still apply to these fake sources (only LOADERS is faked), so
# each must clear its real min_rows (sebi_ia: 800; nse_equity_list: 1500) to land as 'ok'. One of
# the generated rows always has this known key, for tests that look up one specific row.
_KNOWN_IA_REG_NO = "INA000000099"


def _fake_ia(spec):
    rows = [(f"INA{i:09d}", "IA", f"Fake Adviser {i}", f"fake adviser {i}", None, None, None, None, "sebi_ia") for i in range(900)]
    return SourceResult(rows=rows, total=900, matched=900, as_on="2026-10-03", sha256="aaa")


def _fake_equity(spec):
    rows = [(f"FAKE{i}", f"Fake Co {i} Ltd", f"fake co {i} ltd", "INE000000001") for i in range(1600)]
    return SourceResult(rows=rows, total=1600, matched=1600, as_on="2026-10-03", sha256="bbb")


def _fake_fails(spec):
    raise RuntimeError("simulated parse failure")


@pytest.fixture
def fake_universe(monkeypatch):
    """Shrink the driver to two real source ids (sebi_ia, nse_equity_list) with fast fake loaders,
    so build() still reads the real config/sources.yaml (gates, table names) but never touches
    data/manual. Returns nothing; tests call ingest_main.build() directly."""
    monkeypatch.setattr(ingest_main, "REAL_SOURCE_IDS", ["sebi_ia", "nse_equity_list"])
    monkeypatch.setattr(ingest_main, "AGGREGATES", {"sebi_registers": ["sebi_ia"]})
    monkeypatch.setitem(ingest_main.LOADERS, "sebi_ia", _fake_ia)
    monkeypatch.setitem(ingest_main.LOADERS, "nse_equity_list", _fake_equity)


def test_fresh_build_commits_both_sources_and_the_aggregate(tmp_path, fake_universe):
    db_path = tmp_path / "registry.db"
    results = ingest_main.build(db_path, fetch_first=False, only=None)
    assert results["sebi_ia"] == {"status": "ok", "row_count": 900, "as_on": "2026-10-03"}
    assert results["nse_equity_list"] == {"status": "ok", "row_count": 1600, "as_on": "2026-10-03"}

    db = RegistryDB(db_path)
    assert db.data_version == 1
    assert db.source_as_on("sebi_ia") == "2026-10-03"
    assert db.source_as_on("sebi_registers") == "2026-10-03"  # the aggregate, computed from members
    assert db.query("SELECT COUNT(*) AS n FROM intermediary")[0]["n"] == 900
    assert db.one("SELECT reg_no FROM intermediary WHERE reg_no = ?", (_KNOWN_IA_REG_NO,))["reg_no"] == _KNOWN_IA_REG_NO
    db.close()


def test_a_failing_source_keeps_its_previous_rows_and_is_recorded_kept_previous(tmp_path, fake_universe):
    db_path = tmp_path / "registry.db"
    ingest_main.build(db_path, fetch_first=False, only=None)  # build 1: seeds 900 good sebi_ia rows

    ingest_main.LOADERS["sebi_ia"] = _fake_fails
    results = ingest_main.build(db_path, fetch_first=False, only=None)  # build 2: sebi_ia's loader now raises

    assert results["sebi_ia"]["status"] == "kept_previous"
    assert results["sebi_ia"]["row_count"] == 900

    db = RegistryDB(db_path)
    assert db.data_version == 2  # the swap still happened; the table was never emptied
    assert db.query("SELECT COUNT(*) AS n FROM intermediary")[0]["n"] == 900
    db.close()


def test_only_copies_the_untouched_source_verbatim(tmp_path, fake_universe):
    db_path = tmp_path / "registry.db"
    build1 = ingest_main.build(db_path, fetch_first=False, only=None)

    build2 = ingest_main.build(db_path, fetch_first=False, only="sebi_ia")
    assert build2["nse_equity_list"] == build1["nse_equity_list"]  # carried forward unchanged
    assert build2["sebi_ia"]["status"] == "ok"  # re-run, not copied

    db = RegistryDB(db_path)
    # carried forward exactly once, not duplicated by the copy
    assert db.query("SELECT COUNT(*) AS n FROM listed_security")[0]["n"] == 1600
    db.close()


def test_only_without_an_existing_database_refuses_to_run(tmp_path, fake_universe):
    with pytest.raises(SystemExit):
        ingest_main.build(tmp_path / "registry.db", fetch_first=False, only="sebi_ia")


def test_only_with_an_unknown_source_id_refuses_to_run(tmp_path, fake_universe):
    db_path = tmp_path / "registry.db"
    ingest_main.build(db_path, fetch_first=False, only=None)
    with pytest.raises(SystemExit):
        ingest_main.build(db_path, fetch_first=False, only="not_a_real_source")


# ---- one real, slower end-to-end build from the actual data/manual/ tree -----------------------

_PAN_SHAPED = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")

# Every aggregate id a checker can cite in a source chip (LLD; mirrors tests/fixtures/fixture_db.py's
# SOURCES list plus sebi_registers), excluding the two network-fetched feeds: whether those have an
# as_on depends on whether data/cache/feeds/ already holds a download in this environment, which this
# test must not assume either way.
_MUST_HAVE_AS_ON = [
    "sebi_registers", "sebi_ia", "sebi_ra", "sebi_broker_equity", "sebi_broker_fo", "sebi_broker_currency",
    "sebi_broker_commodity", "sebi_dp_cdsl", "sebi_dp_nsdl", "sebi_pms", "sebi_mf", "sebi_aif", "sebi_mb",
    "sebi_rta", "caution_lists", "blocklists", "official_domains", "nse_broker_apps", "nse_broker_social",
    "nse_debarred", "crux_india", "psp_handles", "nse_equity_list",
]


def test_real_end_to_end_build_from_data_manual(tmp_path):
    """Builds from the actual repository data, offline (no --fetch): the exact command the
    hackathon demo runs, just pointed at a throwaway --db path."""
    db_path = tmp_path / "registry.db"
    results = ingest_main.build(db_path, fetch_first=False, only=None)

    assert all(r["status"] in ("ok", "failed", "kept_previous") for r in results.values())
    assert results["sebi_mf"]["row_count"] >= 45  # the one source with a documented pattern_min_rate override

    db = RegistryDB(db_path)
    for source_id in _MUST_HAVE_AS_ON:
        as_on = db.source_as_on(source_id)
        assert as_on, f"{source_id} has no as_on in a from-scratch build of data/manual/"
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", as_on), f"{source_id} as_on {as_on!r} is not an ISO date"

    assert db.query("PRAGMA integrity_check")[0][0] == "ok"

    # Privacy: a PAN (e.g. from debarred.xls) must never survive in clear in any text column.
    tables = [r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type = 'table'")]
    checked_columns = 0
    for table in tables:
        for col in db.query(f"PRAGMA table_info({table})"):
            if col["type"].upper() != "TEXT":
                continue
            checked_columns += 1
            for row in db.query(f"SELECT {col['name']} AS v FROM {table}"):  # noqa: S608 - table/col from PRAGMA, not user input
                if row["v"] and _PAN_SHAPED.search(str(row["v"])):
                    raise AssertionError(f"PAN-shaped value in {table}.{col['name']}: {row['v']!r}")
    assert checked_columns > 10  # sanity: we actually scanned a meaningful number of TEXT columns
    db.close()


def test_prune_blocklist_drops_official_and_popular_platforms(tmp_path):
    """Feeds list whole platforms (google.com, bank domains); a critical signal must never fire on them."""
    import sqlite3

    from satark.ingest.__main__ import SCHEMA, prune_blocklist

    con = sqlite3.connect(tmp_path / "t.db")
    con.executescript(SCHEMA.read_text())
    con.execute("INSERT INTO ingest_run (id, source_id, started_at, status, as_on) VALUES (1, 's', 'x', 'ok', 'x')")
    con.executemany("INSERT INTO blocklist_domain VALUES (?, 'feed', 1)",
                    [("google.com",), ("evil.github.io",), ("axis.bank.in",), ("fake-kite-login.xyz",)])
    con.execute("INSERT INTO official_domain VALUES ('axis.bank.in', 'Axis Bank', 'bank', NULL, 1)")
    con.executemany("INSERT INTO popularity VALUES (?, ?, 1)", [("google.com", 1000), ("github.io", 10000)])
    assert prune_blocklist(con) == 2  # google.com (popular) and axis.bank.in (official)
    # one phishing site on a shared host stays listed; the platform itself does not
    assert sorted(r[0] for r in con.execute("SELECT domain FROM blocklist_domain")) == ["evil.github.io", "fake-kite-login.xyz"]
