"""Hand-curated reference tables: official domains, caution/alert lists, UPI handle map.

Each loader reads a small CSV (and, for official domains, config/brands.yaml too) and applies
the same normalisers the checkers use (satark.infra.norm), so a lookup at check time compares
like with like. These files are small by design -- see their .meta.yaml sidecars for provenance
and, where a list is empty on purpose (nothing verifiable found), why.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

import yaml

from satark.infra.norm import handle_norm, name_norm, phone_norm, registrable_domain, upi_norm
from satark.ingest.gate import SourceResult, sha256_file


def _as_on(path: Path, default: str = "2026-10-03") -> str:
    sidecar = path.with_suffix(path.suffix + ".meta.yaml")
    if sidecar.exists():
        return yaml.safe_load(sidecar.read_text()).get("as_on", default)
    return default


def load_official_domains(spec: dict) -> SourceResult:
    """config/brands.yaml (every brand's domains) + data/manual/official_domains.csv (hand-verified
    exchanges/depositories/AMCs/RTAs), deduplicated by domain -- brands.yaml wins a collision."""
    root = Path(spec["_root"])
    csv_path = root / spec["path"]
    brands_path = root / spec["extra"]
    pattern = re.compile(spec["gates"]["key_pattern"])

    seen: dict[str, tuple] = {}
    total = matched = 0

    brands = yaml.safe_load(brands_path.read_text()).get("brands", [])
    for b in brands:
        for d in b.get("domains", []):
            total += 1
            domain = registrable_domain(d)
            if not domain or not pattern.match(domain):
                continue
            matched += 1
            seen.setdefault(domain, (domain, b["name"], b.get("kind") or "other", b["id"]))

    with csv_path.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            total += 1
            domain = registrable_domain((rec.get("domain") or "").strip())
            if not domain or not pattern.match(domain):
                continue
            matched += 1
            seen.setdefault(domain, (domain, (rec.get("entity_name") or "").strip(), (rec.get("category") or "other").strip(), None))

    return SourceResult(
        rows=list(seen.values()),
        total=total,
        matched=matched,
        as_on=_as_on(csv_path),
        sha256=sha256_file(csv_path, brands_path),
    )


# caution_entries.csv column `value` -> caution_entry.value_norm, by entry_type (LLD §16).
_NORMALISERS: dict[str, Any] = {
    "name": name_norm,
    "phone": phone_norm,
    "domain": registrable_domain,
    "url": registrable_domain,
    "upi": upi_norm,
    "telegram": handle_norm,
    "handle": handle_norm,
    "app": lambda v: v.strip(),
}


def load_caution_entries(spec: dict) -> SourceResult:
    path = Path(spec["_root"]) / spec["path"]

    rows: list[tuple] = []
    total = matched = 0
    with path.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            total += 1
            entry_type = (rec.get("entry_type") or "").strip()
            value = (rec.get("value") or "").strip()
            normalise = _NORMALISERS.get(entry_type)
            list_id = (rec.get("list_id") or "").strip()
            source_url = (rec.get("source_url") or "").strip()
            if not normalise or not value or not list_id or not source_url:
                continue
            matched += 1
            rows.append(
                (
                    list_id,
                    entry_type,
                    normalise(value),
                    (rec.get("display") or value).strip(),
                    (rec.get("published_at") or "").strip() or None,
                    source_url,
                )
            )

    # as_on = the date the list was curated (sidecar), not the newest notice date: a notice from 2025 is
    # still current, and the freshness gate must not reject it as "older" than the previous build
    as_on = _as_on(path)
    return SourceResult(rows=rows, total=total, matched=matched, as_on=as_on, sha256=sha256_file(path))


def load_psp_handles(spec: dict) -> SourceResult:
    path = Path(spec["_root"]) / spec["path"]
    pattern = re.compile(spec["gates"]["key_pattern"])

    rows: list[tuple] = []
    total = matched = 0
    with path.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            total += 1
            handle = (rec.get("handle") or "").strip().lower()
            if not handle or not pattern.match(handle):
                continue
            bank = (rec.get("bank") or "").strip()
            if not bank:
                continue
            matched += 1
            rows.append((handle, bank, (rec.get("app") or "").strip() or None))

    return SourceResult(rows=rows, total=total, matched=matched, as_on=_as_on(path), sha256=sha256_file(path))
