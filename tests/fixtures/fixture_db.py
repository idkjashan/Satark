"""A small registry database with known rows, for checker and harness tests.

Every value here is test data (fictional names and numbers in valid formats), except the
official domains, which mirror config/brands.yaml.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from satark.infra.norm import name_norm, sha256_hex

SCHEMA = Path(__file__).resolve().parents[2] / "satark" / "ingest" / "schema.sql"

AS_ON = "2026-10-03"

INTERMEDIARIES = [
    # reg_no, category, name, trade_name, exchange, valid_from, valid_to, source_id
    ("INA000000001", "IA", "Test Advisors Private Limited", None, None, "2020-01-01", "perpetual", "sebi_ia"),
    ("INH000000002", "RA", "Rajesh Kumar Sharma", None, None, "2021-05-01", "perpetual", "sebi_ra"),
    ("INH000000005", "RA", "Rajesh Sharma Research", None, None, "2022-01-01", "perpetual", "sebi_ra"),
    ("INH000000006", "RA", "Sharma Rajesh Analytics", None, None, "2022-01-01", "perpetual", "sebi_ra"),
    ("INZ000000003", "BROKER", "Example Broking Limited", "ExampleTrade", "NSE", "2019-01-01", "perpetual", "sebi_broker_equity"),
    ("INA000000004", "IA", "Old Adviser", None, None, "2015-01-01", "2020-01-01", "sebi_ia"),
    ("INP000000007", "PMS", "Prudent Portfolio Managers LLP", None, None, "2018-01-01", "perpetual", "sebi_pms"),
]

CAUTION = [
    # list_id, entry_type, value_norm, display, source_url
    ("nse_caution", "name", name_norm("Quick Profit Advisory"), "Quick Profit Advisory", "https://www.nseindia.com/test-notice.pdf"),
    ("nse_caution", "phone", "+919999900000", "+91 99999 00000", "https://www.nseindia.com/test-notice.pdf"),
    ("nse_caution", "domain", "fake-sebi-refund.in", "fake-sebi-refund.in", "https://www.nseindia.com/test-notice.pdf"),
    ("nse_caution", "upi", "scammer@ybl", "scammer@ybl", "https://www.nseindia.com/test-notice.pdf"),
    ("nse_caution", "telegram", "bullrun_vip", "t.me/bullrun_vip", "https://www.nseindia.com/test-notice.pdf"),
]

BLOCKLIST = [("phish-example.xyz", "phishing_database"), ("bad-trade-app.top", "hagezi_tif")]

OFFICIAL = [
    ("sebi.gov.in", "SEBI", "regulator", "sebi"),
    ("nseindia.com", "National Stock Exchange", "exchange", "nse"),
    ("zerodha.com", "Zerodha", "broker", "zerodha"),
    ("groww.in", "Groww", "broker", "groww"),
    ("hdfcbank.com", "HDFC Bank", "bank", "hdfcbank"),
    ("sbi.bank.in", "State Bank of India", "bank", "sbi"),
    ("rbi.org.in", "Reserve Bank of India", "regulator", "rbi"),
]

APPS = [
    ("com.zerodha.kite3", "Kite by Zerodha", "ZERODHA BROKING LIMITED", "Zerodha", "nse_broker_apps"),
    ("com.nextbillion.groww", "Groww", "GROWW INVEST TECH PRIVATE LIMITED", "Groww", "nse_broker_apps"),
]

SOCIAL = [
    ("x", "zerodhaonline", "ZERODHA BROKING LIMITED", "broker"),
    ("youtube", "zerodhaonline", "ZERODHA BROKING LIMITED", "broker"),
    ("telegram", "groww_official", "GROWW INVEST TECH PRIVATE LIMITED", "broker"),
]

DEBARRED = [
    # name, pan, order_date, order_ref, period, revoked
    ("Fraud Operator One", "ABCPF1234K", "2026-09-28", "NSE/INVG/00001", "3 years", 0),
    ("Pump Masters Private Limited", "AAACP1234Q", "2025-01-15", "NSE/INVG/00002", "5 years", 0),
]

POPULARITY = [("zerodha.com", 1000), ("groww.in", 1000), ("sebi.gov.in", 5000), ("hdfcbank.com", 1000)]

PSP = [
    ("okaxis", "Axis Bank", "Google Pay"),
    ("oksbi", "State Bank of India", "Google Pay"),
    ("ybl", "Yes Bank", "PhonePe"),
    ("paytm", "Paytm Payments Bank", "Paytm"),
    ("validhdfc", "HDFC Bank", None),
    ("validicici", "ICICI Bank", None),
]

LISTED = [("RELIANCE", "Reliance Industries Limited", "INE002A01018"), ("TCS", "Tata Consultancy Services Limited", "INE467B01029")]

SOURCES = [
    "sebi_ia", "sebi_ra", "sebi_broker_equity", "sebi_pms", "caution_lists", "blocklists", "official_domains",
    "nse_broker_apps", "nse_broker_social", "nse_debarred", "crux_india", "psp_handles", "nse_equity_list",
]


def build_fixture_db(path: Path | str) -> Path:
    path = Path(path)
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.executescript(SCHEMA.read_text())
    run_ids: dict[str, int] = {}
    for sid in SOURCES:
        cur = con.execute(
            "INSERT INTO ingest_run (source_id, started_at, finished_at, status, row_count, sha256, as_on) "
            "VALUES (?, ?, ?, 'ok', 1, 'test', ?)",
            (sid, f"{AS_ON}T00:00:00Z", f"{AS_ON}T00:01:00Z", AS_ON),
        )
        run_ids[sid] = cur.lastrowid
    for reg, cat, name, trade, exch, vf, vt, sid in INTERMEDIARIES:
        con.execute(
            "INSERT INTO intermediary (reg_no, category, name, name_norm, trade_name, exchange, valid_from, valid_to, source_id, run_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (reg, cat, name, name_norm(name), trade, exch, vf, vt, sid, run_ids[sid]),
        )
    con.execute("INSERT INTO intermediary_fts (intermediary_fts) VALUES ('rebuild')")
    for list_id, et, vn, disp, url in CAUTION:
        con.execute(
            "INSERT INTO caution_entry (list_id, entry_type, value_norm, display, published_at, source_url, run_id) VALUES (?,?,?,?,?,?,?)",
            (list_id, et, vn, disp, AS_ON, url, run_ids["caution_lists"]),
        )
    con.executemany("INSERT INTO blocklist_domain VALUES (?,?,?)", [(d, f, run_ids["blocklists"]) for d, f in BLOCKLIST])
    con.executemany(
        "INSERT INTO official_domain VALUES (?,?,?,?,?)", [(d, n, c, b, run_ids["official_domains"]) for d, n, c, b in OFFICIAL]
    )
    con.executemany("INSERT INTO app_registry VALUES (?,?,?,?,?,?)", [(*a, run_ids["nse_broker_apps"]) for a in APPS])
    con.executemany("INSERT INTO social_handle VALUES (?,?,?,?,?)", [(*s, run_ids["nse_broker_social"]) for s in SOCIAL])
    for name, pan, od, ref, period, rev in DEBARRED:
        con.execute(
            "INSERT INTO debarred (name, name_norm, pan_sha256, order_date, order_ref, period, revoked, run_id) VALUES (?,?,?,?,?,?,?,?)",
            (name, name_norm(name), sha256_hex(pan.upper()), od, ref, period, rev, run_ids["nse_debarred"]),
        )
    con.executemany("INSERT INTO popularity VALUES (?,?,?)", [(d, b, run_ids["crux_india"]) for d, b in POPULARITY])
    con.executemany("INSERT INTO psp_handle VALUES (?,?,?,?)", [(*p, run_ids["psp_handles"]) for p in PSP])
    con.executemany(
        "INSERT INTO listed_security VALUES (?,?,?,?,?)",
        [(s, n, name_norm(n), i, run_ids["nse_equity_list"]) for s, n, i in LISTED],
    )
    con.executemany("INSERT INTO meta VALUES (?,?)", [("data_version", "1"), ("built_at", f"{AS_ON}T00:02:00Z")])
    con.commit()
    con.close()
    return path


if __name__ == "__main__":  # pragma: no cover
    import sys

    print(build_fixture_db(sys.argv[1] if len(sys.argv) > 1 else "fixture.db"))
