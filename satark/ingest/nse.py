"""NSE lists: SEBI-debarred entities, brokers' apps and social handles, listed equities.

NSE's terms bar automated collection, so every file here is a hand-saved snapshot
(data/manual/nse/*, with a .meta.yaml sidecar); this module only parses what is already on disk.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import xlrd
import yaml

from satark.infra.norm import handle_norm, name_norm, sha256_hex
from satark.ingest.gate import SourceResult, sha256_file

_PAN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_PAN_EMBEDDED = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
# A few hundred debarred.xls rows from the 2000s carry a full address (and sometimes the PAN
# itself) inside the "Entity / Individual Name" cell, e.g.
# "Jayesh V Merchant (Address : 3 New Jitendra Society, ..., PAN : AALPM9050F )". Keeping that in
# `name` would both leak a PAN in clear and leave the name useless for display/matching.
_NAME_ADDRESS_SUFFIX = re.compile(r"\s*\(\s*address\s*:.*\)\s*$", re.IGNORECASE | re.DOTALL)


def _clean_name(raw_name: str) -> tuple[str, str | None]:
    """-> (display-safe name, a PAN found embedded in it, or None). Never leaves a PAN in `name`."""
    embedded = _PAN_EMBEDDED.search(raw_name)
    name = _NAME_ADDRESS_SUFFIX.sub("", raw_name).strip()
    if embedded:
        name = _PAN_EMBEDDED.sub("", name).strip()
    return name, (embedded.group(0) if embedded else None)

# NSE broker_social.json field -> schema's social_handle.platform
_SOCIAL_FIELDS = {"twitter": "x", "facebook": "facebook", "instagram": "instagram", "linkedIn": "linkedin", "youtube": "youtube"}


def _as_on(path: Path, default: str = "2026-10-03") -> str:
    sidecar = path.with_suffix(path.suffix + ".meta.yaml")
    if sidecar.exists():
        return yaml.safe_load(sidecar.read_text()).get("as_on", default)
    return default


def _parse_xls_date(value: object, cell_type: int, datemode: int) -> str | None:
    """debarred.xls mixes Excel date serials (recent rows) and text dates (old rows)."""
    if cell_type == xlrd.XL_CELL_DATE and value:
        try:
            return xlrd.xldate_as_datetime(value, datemode).date().isoformat()  # type: ignore[arg-type]
        except xlrd.xldate.XLDateError:
            return None
    s = str(value).strip()
    if not s or s == "-":
        return None
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%d-%B-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def load_debarred(spec: dict) -> SourceResult:
    path = Path(spec["_root"]) / spec["path"]
    book = xlrd.open_workbook(str(path))
    sh = book.sheet_by_index(0)
    pattern = re.compile(spec["gates"]["key_pattern"])

    rows: list[tuple] = []
    total = matched = 0
    for r in range(1, sh.nrows):  # row 0 is the header
        name, embedded_pan = _clean_name(str(sh.cell_value(r, 2)).strip())
        total += 1
        if not pattern.match(name):
            continue
        pan = str(sh.cell_value(r, 3)).strip().upper()
        if not _PAN.match(pan):
            pan = embedded_pan or pan  # a few old rows only carry the PAN inside the name cell
        pan_sha = sha256_hex(pan) if pan and _PAN.match(pan) else None
        order_date = _parse_xls_date(sh.cell_value(r, 0), sh.cell_type(r, 0), book.datemode)
        period = str(sh.cell_value(r, 6)).strip() or None
        order_ref = str(sh.cell_value(r, 7)).strip() or None
        revocation_ref = str(sh.cell_value(r, 9)).strip()
        revoked = 1 if revocation_ref and revocation_ref != "-" else 0
        matched += 1
        rows.append((name, name_norm(name), pan_sha, order_date, order_ref, period, revoked))

    return SourceResult(rows=rows, total=total, matched=matched, as_on=_as_on(path), sha256=sha256_file(path))


def load_broker_apps(spec: dict) -> SourceResult:
    path = Path(spec["_root"]) / spec["path"]
    records = json.loads(path.read_text(encoding="utf-8"))
    pattern = re.compile(spec["gates"]["key_pattern"])

    seen: dict[str, tuple] = {}
    total = matched = 0
    for rec in records:
        link = str(rec.get("androidAppLink") or "").strip()
        if "play.google.com" not in link.lower():
            continue  # not a Play Store listing (no app, a shortlink, an APK, a BSE-only app...):
            # nothing a package-id pattern could match, same as having no app at all
        total += 1
        package_id = (parse_qs(urlparse(link).query).get("id") or [""])[0]
        if not package_id or not pattern.match(package_id):
            continue
        matched += 1
        seen[package_id] = (
            package_id,
            rec.get("productName") or None,
            rec.get("memberName") or "",
            rec.get("devName") or None,
            spec["_source_id"],
        )

    return SourceResult(
        rows=list(seen.values()), total=total, matched=matched, as_on=_as_on(path), sha256=sha256_file(path)
    )


def load_broker_social(spec: dict) -> SourceResult:
    path = Path(spec["_root"]) / spec["path"]
    records = json.loads(path.read_text(encoding="utf-8"))

    seen: dict[tuple[str, str], tuple] = {}
    total = matched = 0
    for rec in records:
        member = str(rec.get("memberName") or "").strip()
        total += 1
        if not member:  # entity_name is NOT NULL: a row with no member name is unusable
            continue
        matched += 1
        for field, platform in _SOCIAL_FIELDS.items():
            raw = str(rec.get(field) or "").strip()
            if not raw or raw.upper() == "NA":
                continue
            handle = handle_norm(raw)
            if handle:
                seen[(platform, handle)] = (platform, handle, member, "broker")

    return SourceResult(
        rows=list(seen.values()), total=total, matched=matched, as_on=_as_on(path), sha256=sha256_file(path)
    )


def load_equity_list(spec: dict) -> SourceResult:
    path = Path(spec["_root"]) / spec["path"]
    pattern = re.compile(spec["gates"]["key_pattern"])

    seen: dict[str, tuple] = {}
    total = matched = 0
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = {name.strip(): name for name in reader.fieldnames or []}  # NSE's CSV pads some headers with a space
        for rec in reader:
            symbol = str(rec.get(header.get("SYMBOL", "SYMBOL"), "")).strip()
            total += 1
            if not symbol or not pattern.match(symbol):
                continue
            name = str(rec.get(header.get("NAME OF COMPANY", "NAME OF COMPANY"), "")).strip()
            if not name:
                continue
            isin = str(rec.get(header.get("ISIN NUMBER", "ISIN NUMBER"), "")).strip() or None
            matched += 1
            seen[symbol] = (symbol, name, name_norm(name), isin)

    return SourceResult(
        rows=list(seen.values()), total=total, matched=matched, as_on=_as_on(path), sha256=sha256_file(path)
    )
