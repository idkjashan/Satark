"""satark.ingest.gate: the pass/fail arithmetic (LLD §16) and the copy-previous SQL helpers."""

from __future__ import annotations

import sqlite3

import pytest

from satark.ingest.gate import (
    bulk_insert,
    check_gate,
    copy_previous,
    insert_ingest_run,
    previous_run,
    sha256_file,
)
from tests.fixtures.fixture_db import AS_ON, build_fixture_db

# ---- check_gate: pure arithmetic, no files or database ----------------------------------------


def test_gate_passes_with_healthy_numbers():
    passed, reason = check_gate(
        total=1000, matched=995, row_count=995, min_rows=100, max_drop_pct=5,
        as_on="2026-10-03", prev_row_count=None, prev_as_on=None,
    )
    assert passed and reason == ""


def test_gate_fails_below_pattern_rate():
    passed, reason = check_gate(
        total=100, matched=90, row_count=90, min_rows=1, max_drop_pct=100,
        as_on="2026-10-03", prev_row_count=None, prev_as_on=None,
    )
    assert not passed
    assert "key pattern" in reason


def test_gate_pattern_min_rate_override_is_honoured():
    # 60/61 = 98.36%: fails the global 99% floor, passes a documented 98% override.
    passed, reason = check_gate(
        total=61, matched=60, row_count=60, min_rows=1, max_drop_pct=100,
        as_on="2026-10-03", prev_row_count=None, prev_as_on=None, pattern_min_rate=0.98,
    )
    assert passed, reason


def test_gate_fails_below_min_rows():
    passed, reason = check_gate(
        total=10, matched=10, row_count=10, min_rows=50, max_drop_pct=100,
        as_on="2026-10-03", prev_row_count=None, prev_as_on=None,
    )
    assert not passed
    assert "min_rows" in reason


def test_gate_empty_source_with_zero_min_rows_passes():
    """A header-only caution_entries.csv (or an empty blocklist_local.txt) is a valid 'ok', not a
    gate failure -- the whole point of shipping it empty rather than with fabricated rows."""
    passed, reason = check_gate(
        total=0, matched=0, row_count=0, min_rows=0, max_drop_pct=100,
        as_on="2026-10-03", prev_row_count=None, prev_as_on=None,
    )
    assert passed, reason


def test_gate_fails_on_excess_drop_vs_previous_run():
    passed, reason = check_gate(
        total=100, matched=100, row_count=50, min_rows=1, max_drop_pct=10,
        as_on="2026-10-03", prev_row_count=100, prev_as_on="2026-09-01",
    )
    assert not passed
    assert "dropped" in reason


def test_gate_small_drop_within_tolerance_passes():
    passed, reason = check_gate(
        total=100, matched=100, row_count=96, min_rows=1, max_drop_pct=10,
        as_on="2026-10-03", prev_row_count=100, prev_as_on="2026-09-01",
    )
    assert passed, reason


def test_gate_fails_when_as_on_regresses():
    passed, reason = check_gate(
        total=10, matched=10, row_count=10, min_rows=1, max_drop_pct=100,
        as_on="2026-01-01", prev_row_count=None, prev_as_on="2026-09-01",
    )
    assert not passed
    assert "older" in reason


def test_gate_row_count_not_matched_drives_the_drop_check():
    """A fan-out source (one input row -> several table rows, e.g. social_handle) must compare
    row_count against the previous run's row_count, not the input-level `matched` count -- those
    are different units and comparing them produces a false 'dropped' failure."""
    passed, reason = check_gate(
        total=582, matched=582, row_count=1751, min_rows=1, max_drop_pct=10,
        as_on="2026-10-03", prev_row_count=1751, prev_as_on="2026-09-01",
    )
    assert passed, reason


# ---- previous_run / copy_previous / bulk_insert: real SQLite, via the fixed test fixture -------


@pytest.fixture
def old_db_path(tmp_path):
    return build_fixture_db(tmp_path / "old.db")


@pytest.fixture
def next_con(tmp_path, old_db_path):
    from satark.ingest.__main__ import ROOT, SCHEMA

    assert ROOT.name == "satark" or (ROOT / "satark").is_dir()  # sanity: resolved to the repo root
    con = sqlite3.connect(tmp_path / "next.db")
    con.executescript(SCHEMA.read_text())
    con.execute("ATTACH DATABASE ? AS old", (str(old_db_path),))
    yield con
    con.close()


def test_previous_run_reads_the_attached_database(next_con):
    prev = previous_run(next_con, "sebi_ia")
    assert prev is not None
    assert prev["status"] == "ok"
    assert prev["row_count"] == 1
    assert prev["as_on"] == AS_ON


def test_previous_run_is_none_for_an_unknown_source(next_con):
    assert previous_run(next_con, "no_such_source") is None


def test_copy_previous_carries_rows_and_records_a_new_ingest_run(next_con):
    copied = copy_previous(next_con, "sebi_ia", "intermediary", "2026-10-04T00:00:00Z")
    assert copied == {"status": "ok", "row_count": 1, "as_on": AS_ON}
    # the fixture's sebi_ia run_id covers two intermediary rows (both IA entries in fixture_db.py);
    # copy_previous copies by run_id, so both come along even though the fixture's own row_count
    # field is a hardcoded placeholder unrelated to the real row count.
    rows = {r[0] for r in next_con.execute("SELECT reg_no FROM intermediary").fetchall()}
    assert rows == {"INA000000001", "INA000000004"}


def test_copy_previous_force_status_overrides_the_carried_forward_status(next_con):
    copied = copy_previous(next_con, "sebi_ia", "intermediary", "2026-10-04T00:00:00Z", force_status="kept_previous")
    assert copied["status"] == "kept_previous"
    (status,) = next_con.execute("SELECT status FROM ingest_run WHERE source_id = 'sebi_ia' ORDER BY id DESC LIMIT 1").fetchone()
    assert status == "kept_previous"


def test_bulk_insert_appends_run_id_in_column_order(next_con):
    run_id = insert_ingest_run(next_con, "nse_equity_list", "2026-10-04T00:00:00Z", "ok", 1, "deadbeef", "2026-10-04")
    bulk_insert(next_con, "listed_security", [("TEST", "Test Co", "test co", "INE000000000")], run_id)
    row = next_con.execute("SELECT symbol, name, name_norm, isin, run_id FROM listed_security WHERE symbol = 'TEST'").fetchone()
    assert row == ("TEST", "Test Co", "test co", "INE000000000", run_id)


def test_sha256_file_is_order_sensitive_and_matches_manual_hash(tmp_path):
    import hashlib

    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("hello")
    b.write_text("world")
    expected = hashlib.sha256(b"hello" + b"world").hexdigest()
    assert sha256_file(a, b) == expected
    assert sha256_file(b, a) != expected
