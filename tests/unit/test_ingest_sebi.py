"""satark.ingest.sebi: title-date parsing and the 20/22-column row parser (pure, in-memory)."""

from __future__ import annotations

from satark.ingest.sebi import parse_row, parse_title_as_on

# A 20-column row shape, positions matching data/manual/sebi/intm_*.xls (row 2's header).
_ROW20 = [
    "KAVITHA MENON", "INA000000037", "contact", "address", "email@example.com", "9876543210", "",
    "MUMBAI", "MAHARASHTRA", "400022", "corr address", "", "", "", "MUMBAI", "MAHARASHTRA", "400022",
    "Aug 01, 2013", "Perpetual", "",
]
_ROW22 = [*_ROW20, "BOMBAY STOCK EXCHANGE LIMITED", "Example Trade Name"]


def test_parse_title_as_on_reads_the_trailing_date():
    assert parse_title_as_on("Research Analyst as on Oct 03, 2026", "fallback") == "2026-10-03"


def test_parse_title_as_on_falls_back_when_the_title_has_no_date():
    assert parse_title_as_on("Research Analyst", "2026-10-03") == "2026-10-03"
    assert parse_title_as_on("", "2026-10-03") == "2026-10-03"


def test_parse_row_drops_personal_columns():
    row = parse_row(_ROW20, has_broker_cols=False)
    assert row == ("INA000000037", "KAVITHA MENON", None, None, "2013-08-01", "perpetual")
    # none of contact/address/email/phone/city/state/pincode survive
    assert "email@example.com" not in row
    assert "9876543210" not in row


def test_parse_row_blank_name_is_dropped():
    bad = list(_ROW20)
    bad[0] = "   "
    assert parse_row(bad, has_broker_cols=False) is None


def test_parse_row_broker_columns_carry_exchange_and_trade_name():
    row = parse_row(_ROW22, has_broker_cols=True)
    assert row == (
        "INA000000037", "KAVITHA MENON", "Example Trade Name", "BOMBAY STOCK EXCHANGE LIMITED",
        "2013-08-01", "perpetual",
    )


def test_parse_row_non_broker_file_ignores_trailing_columns_even_if_present():
    # has_broker_cols=False must never read columns 20/21, even if the row happens to have them
    row = parse_row(_ROW22, has_broker_cols=False)
    assert row[2:4] == (None, None)


def test_parse_row_reg_no_is_normalised():
    row = parse_row(["Name", " ina 000 099999 ", *[""] * 18], has_broker_cols=False)
    assert row[0] == "INA000099999"


def test_parse_row_unparsable_valid_to_is_dropped_not_guessed():
    row = parse_row(["Name", "INA000000001", *[""] * 15, "Aug 01, 2013", "not a date", ""], has_broker_cols=False)
    assert row[4] == "2013-08-01"
    assert row[5] is None
