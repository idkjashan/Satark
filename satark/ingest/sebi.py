"""SEBI registered-intermediary exports (LLD §14.1; Satark-Sources.md SEBI-1).

Each category is one BIFF8 .xls: row 0 a title ("<Category> as on <Mon DD, YYYY>"), row 1 a
group header, row 2 column headers, row 3+ data (20 columns; brokers add 2 more: Exchange Name,
Trade Name). Every personal column (contact person, address, email, phone, fax, city, state,
pincode -- both the registered and "correspondence" copies) is dropped at parse time; only
reg_no, name, trade_name, exchange and the validity dates survive into the registry.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import xlrd
import yaml

from satark.infra.norm import name_norm, reg_norm
from satark.ingest.gate import SourceResult, sha256_file

_TITLE_DATE = re.compile(r"as on\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s*$")

# Fixed column positions, same across all 13 files (0-indexed; row 2 is the header row).
_NAME, _REG_NO, _VALID_FROM, _VALID_TO = 0, 1, 17, 18
_EXCHANGE, _TRADE_NAME = 20, 21  # brokers only (22-column files)


def parse_title_as_on(title: str, fallback: str) -> str:
    """'Research Analyst as on Oct 03, 2026' -> '2026-10-03'. Falls back when the title is
    missing its trailing date (some exports truncate the title)."""
    m = _TITLE_DATE.search(title or "")
    if not m:
        return fallback
    try:
        return datetime.strptime(m.group(1), "%b %d, %Y").date().isoformat()
    except ValueError:
        return fallback


def _parse_date(value: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    if value.lower() == "perpetual":
        return "perpetual"
    try:
        return datetime.strptime(value, "%b %d, %Y").date().isoformat()
    except ValueError:
        return None  # an unparsable date is dropped, not guessed


def parse_row(cells: list, has_broker_cols: bool) -> tuple | None:
    """One data row's cell values -> (reg_no, name, trade_name, exchange, valid_from, valid_to).

    None means the row is not even structurally usable (no name -- schema requires one): dropped
    before the key-pattern gate, same as a row whose reg_no fails the pattern.
    """
    name = str(cells[_NAME]).strip()
    if not name:
        return None
    reg_no = reg_norm(str(cells[_REG_NO]))
    valid_from = _parse_date(str(cells[_VALID_FROM])) if len(cells) > _VALID_FROM else None
    valid_to = _parse_date(str(cells[_VALID_TO])) if len(cells) > _VALID_TO else None
    trade_name = exchange = None
    if has_broker_cols and len(cells) > _TRADE_NAME:
        exchange = str(cells[_EXCHANGE]).strip() or None
        trade_name = str(cells[_TRADE_NAME]).strip() or None
    return (reg_no, name, trade_name, exchange, valid_from, valid_to)


def _as_on_fallback(path: Path) -> str:
    sidecar = path.with_suffix(path.suffix + ".meta.yaml")
    if sidecar.exists():
        return yaml.safe_load(sidecar.read_text()).get("as_on", "2026-10-03")
    return "2026-10-03"


def load(spec: dict) -> SourceResult:
    path = Path(spec["_root"]) / spec["path"]
    book = xlrd.open_workbook(str(path))
    sh = book.sheet_by_index(0)
    as_on = parse_title_as_on(str(sh.cell_value(0, 0)), _as_on_fallback(path))
    has_broker_cols = sh.ncols >= 22
    pattern = re.compile(spec["gates"]["key_pattern"])
    category = spec["category"]
    source_id = spec["_source_id"]

    rows: list[tuple] = []
    total = matched = 0
    for r in range(3, sh.nrows):
        cells = [sh.cell_value(r, c) for c in range(sh.ncols)]
        total += 1
        parsed = parse_row(cells, has_broker_cols)
        if parsed is None:
            continue
        reg_no, name, trade_name, exchange, valid_from, valid_to = parsed
        if not pattern.match(reg_no):
            continue
        matched += 1
        rows.append((reg_no, category, name, name_norm(name), trade_name, exchange, valid_from, valid_to, source_id))

    return SourceResult(rows=rows, total=total, matched=matched, as_on=as_on, sha256=sha256_file(path))
