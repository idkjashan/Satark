"""satark.ingest.nse: the debarred-date parser (pure) and the four NSE loaders against the real,
small snapshot files already in data/manual/nse/ (no network, no fabricated .xls needed)."""

from __future__ import annotations

from pathlib import Path

import xlrd

from satark.ingest.nse import (
    _PAN,
    _clean_name,
    _parse_xls_date,
    load_broker_apps,
    load_broker_social,
    load_debarred,
    load_equity_list,
)

ROOT = Path(__file__).resolve().parents[2]


def _spec(path: str, key_pattern: str, **extra) -> dict:
    return {"_root": ROOT, "path": path, "gates": {"key_pattern": key_pattern}, **extra}


# ---- _parse_xls_date: pure, no file needed -----------------------------------------------------


def test_parse_xls_date_excel_serial():
    book = xlrd.open_workbook(str(ROOT / "data/manual/nse/debarred.xls"))
    assert _parse_xls_date(46293.0, xlrd.XL_CELL_DATE, book.datemode) == "2026-09-28"


def test_parse_xls_date_text_four_digit_year():
    assert _parse_xls_date("01-FEB-2004", xlrd.XL_CELL_TEXT, 0) == "2004-02-01"


def test_parse_xls_date_text_two_digit_year():
    assert _parse_xls_date("04-FEB-10", xlrd.XL_CELL_TEXT, 0) == "2010-02-04"


def test_parse_xls_date_blank_or_dash_is_none():
    assert _parse_xls_date("", xlrd.XL_CELL_TEXT, 0) is None
    assert _parse_xls_date("-", xlrd.XL_CELL_TEXT, 0) is None


def test_pan_pattern():
    assert _PAN.match("ABCPF1234K")
    assert not _PAN.match("PAN Not Provided")
    assert not _PAN.match("-")


# ---- _clean_name: some real debarred.xls rows carry a PAN (and a full address) in the name ----


def test_clean_name_strips_a_pan_appended_directly_after_the_name():
    name, pan = _clean_name("Mr. Sajeve Bhushan Deora ABBPD0803C")
    assert name == "Mr. Sajeve Bhushan Deora"
    assert pan == "ABBPD0803C"


def test_clean_name_strips_a_trailing_address_block_and_its_embedded_pan():
    raw = "Jayesh V Merchant (Address : 3 New Jitendra Society, Vile Parle (W), RTA Folio No: --, PAN : AALPM9050F )"
    name, pan = _clean_name(raw)
    assert name == "Jayesh V Merchant"
    assert pan == "AALPM9050F"
    assert "AALPM9050F" not in name
    assert "Address" not in name


def test_clean_name_leaves_an_ordinary_name_untouched():
    name, pan = _clean_name("5PAISA CAPITAL LIMITED")
    assert name == "5PAISA CAPITAL LIMITED"
    assert pan is None


# ---- loaders against the real (small) snapshot files -------------------------------------------


def test_load_debarred_hashes_pan_and_never_keeps_it_in_clear():
    result = load_debarred(_spec("data/manual/nse/debarred.xls", r"^.{2,}$"))
    assert result.total > 11000
    assert result.matched / result.total > 0.99  # a handful of rows have no usable name
    assert len(result.rows) == result.matched
    for _name, _name_norm, pan_sha, *_ in result.rows:
        if pan_sha is not None:
            assert len(pan_sha) == 64
            assert all(c in "0123456789abcdef" for c in pan_sha)


def test_load_debarred_revoked_flag_follows_the_revocation_circular_column():
    result = load_debarred(_spec("data/manual/nse/debarred.xls", r"^.{2,}$"))
    assert any(row[-1] == 1 for row in result.rows), "expected at least one revoked entry"
    assert any(row[-1] == 0 for row in result.rows)


def test_load_broker_apps_only_counts_real_play_store_links():
    result = load_broker_apps(_spec("data/manual/nse/broker_apps.json", r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$", _source_id="nse_broker_apps"))
    assert result.total < 619  # "NA", shortlinks, APKs etc. are excluded from the denominator
    assert result.matched / result.total > 0.99
    package_ids = [r[0] for r in result.rows]
    assert "com.wave.fortune" in package_ids
    assert len(package_ids) == len(set(package_ids))  # deduplicated by package_id
    assert all(r[4] == "nse_broker_apps" for r in result.rows)


def test_load_broker_social_platform_mapping_and_handle_norm():
    result = load_broker_social(_spec("data/manual/nse/broker_social.json", r"^.+$"))
    assert result.total == result.matched == 582
    by_platform = {}
    for platform, handle, member, kind in result.rows:
        by_platform.setdefault(platform, set()).add((handle, member))
        assert kind == "broker"
    assert ("kediacapital", "KEDIA CAPITAL SERVICES PRIVATE LIMITED") in by_platform["x"]
    assert "facebook" in by_platform and "youtube" in by_platform
    assert "telegram" not in by_platform  # NSE's file has no telegram column


def test_load_equity_list_strips_header_whitespace_and_dedupes():
    result = load_equity_list(_spec("data/manual/nse/EQUITY_L.csv", r"^[A-Z0-9&-]+$"))
    assert result.total > 2500
    symbols = {r[0] for r in result.rows}
    assert "RELIANCE" in symbols or "TCS" in symbols or len(symbols) > 2000
    assert len(symbols) == len(result.rows)  # PK-safe: no duplicate symbols
